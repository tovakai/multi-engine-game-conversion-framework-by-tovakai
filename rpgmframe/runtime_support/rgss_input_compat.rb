# Compatibility for legacy RGSS Windows input scripts on mkxp-z / modern Ruby.
# Native input remains the source of keyboard and controller state. No Steam
# APIs are emulated here. Load after mkxp-z's win32_wrap.rb.
require 'fiddle'

unless defined?(DL)
  module DL
    @allocations = {}
    def self.malloc(size)
      pointer = Fiddle::Pointer.malloc(Integer(size), Fiddle::RUBY_FREE)
      pointer[0, pointer.size] = "\0" * pointer.size
      @allocations[pointer.to_i] = pointer
      pointer.to_i
    end
    def self.allocation(address)
      @allocations.fetch(Integer(address))
    end
    class CPtr
      def initialize(address, size)
        @pointer = DL.allocation(address)
        @size = Integer(size)
        raise ArgumentError, 'pointer exceeds allocation' if @size > @pointer.size || @size < 0
      end
      def to_i; @pointer.to_i; end
      def [](offset, length = nil)
        offset = Integer(offset)
        count = length.nil? ? 1 : Integer(length)
        raise IndexError, 'pointer read out of bounds' if offset < 0 || count < 0 || offset + count > @size
        value = @pointer[offset, count]
        length.nil? ? value.getbyte(0) : value
      end
      def to_s; @pointer[0, @size]; end
    end
  end
end

module MEGCFBTRGSSInput
  NATIVE_UPDATE = Input.method(:update)
  NATIVE_PRESS = Input.method(:press?)
  XINPUT_BUTTONS = {0 => 0x1000, 1 => 0x2000, 2 => 0x4000, 3 => 0x8000,
    4 => 0x20, 6 => 0x10, 7 => 0x40, 8 => 0x80, 9 => 0x100,
    10 => 0x200, 11 => 1, 12 => 2, 13 => 4, 14 => 8}.freeze
  def self.write_buffer(destination, bytes)
    if destination.is_a?(String)
      raise ArgumentError, 'output buffer too small' if destination.bytesize < bytes.bytesize
      destination[0, bytes.bytesize] = bytes
    else
      pointer = DL.allocation(destination.to_i)
      raise ArgumentError, 'output buffer too small' if pointer.size < bytes.bytesize
      pointer[0, bytes.bytesize] = bytes
    end
  end
  def self.keyboard(destination)
    bytes = "\0" * 256
    if Input.const_defined?(:GetKeyboardState, false)
      text_mode = Input.const_defined?(:ToUnicodeEx, false)
      Input.text_input = true if text_mode
      NATIVE_UPDATE.call
      @text = Input.gets if text_mode
    end
    # Refresh the upstream wrapper's cache even when a game replaces update.
    $win32KeyStates = Input.raw_key_states
    Scancodes::WIN32.each do |name, code|
      mouse = {LBUTTON: :MOUSELEFT, RBUTTON: :MOUSERIGHT, MBUTTON: :MOUSEMIDDLE}[name]
      pressed = mouse ? NATIVE_PRESS.call(Input.const_get(mouse)) : common_keystate(code) == 1
      bytes.setbyte(code, pressed ? 0x80 : 0)
    end
    write_buffer(destination, bytes)
    1
  end
  def self.xinput(index, destination)
    return 1167 unless index == 0 && Input::Controller.connected?
    buttons = Input::Controller.raw_button_states
    mask = XINPUT_BUTTONS.inject(0) { |result, pair| result | (buttons[pair[0]] ? pair[1] : 0) }
    triggers = Input::Controller.axes_trigger.map { |value| [[(value * 255).round, 0].max, 255].min }
    axes = (Input::Controller.axes_left + Input::Controller.axes_right).each_with_index.map do |value, i|
      value = -value if i.odd?
      [[(value * 32767).round, -32768].max, 32767].min
    end
    state = [mask, *triggers, *axes].pack('vCCs<s<s<s<')
    if @previous_state != state
      @packet = ((@packet || 0) + 1) & 0xffffffff
      @packet = 1 if @packet == 0
      @previous_state = state
    end
    write_buffer(destination, [@packet].pack('V') + state)
    0
  end
  def self.text
    text = @text || ''
    @text = ''
    text
  end
  module Text
    def UTF8String
      return MEGCFBTRGSSInput.text if Input.const_defined?(:ToUnicodeEx, false)
      super
    end
  end
  module Calls
    def call(*args)
      dll = @dll.to_s.downcase.sub(/\.dll\z/, '')
      if dll == 'user32' && @func == 'GetKeyboardState'
        return MEGCFBTRGSSInput.keyboard(args.fetch(0))
      end
      if dll.match?(/\Axinput(?:1_[1-4]|9_1_0)\z/)
        return MEGCFBTRGSSInput.xinput(*args) if @func == 'XInputGetState'
        return 50 if @func == 'XInputSetState' # Native binding exposes no rumble API.
      end
      super
    end
  end
end
Win32API.prepend(MEGCFBTRGSSInput::Calls)
Input.singleton_class.prepend(MEGCFBTRGSSInput::Text)

# One audited legacy Ruby syntax incompatibility in The Last Sovereign 1.2.2.
# Apply only to the exact reviewed script, in memory after mkxp-z decompression.
# Neither the archive nor any source files are written.
if defined?($RGSS_SCRIPTS) && $RGSS_SCRIPTS.is_a?(Array)
  require 'digest'
  require 'digest/sha2'
  $RGSS_SCRIPTS.each do |entry|
    next unless entry.is_a?(Array) && entry[1] == 'Battle Bust Config' && entry[3].is_a?(String)
    next unless Digest::SHA256.hexdigest(entry[3]) == 'b02dfe70d716a99e02b90d8c9b198c9e77711fcc71b36b3e7bd8851bd7480346'
    before = 'return "SimonGreenHealHealing",'
    raise 'Audited Ruby adaptation no longer matches' unless entry[3].scan(before).size == 1
    entry[3] = entry[3].sub(before, 'return "SimonGreenHealHealing"')
  end
end
