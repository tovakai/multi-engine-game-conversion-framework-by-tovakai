# Synthetic game/API fixture; no commercial scripts or assets.
module Input
  MOUSELEFT = 1; MOUSERIGHT = 2; MOUSEMIDDLE = 3
  class << self
    attr_accessor :text_input, :keys, :characters
    def update; @updates = (@updates || 0) + 1; end
    def updates; @updates || 0; end
    def press?(key); key == MOUSELEFT; end
    def raw_key_states; @keys || []; end
    def gets; value = @characters || ''; @characters = ''; value; end
  end
  module Controller
    class << self
      attr_accessor :connected, :buttons, :axes, :triggers
      def connected?; @connected; end
      def raw_button_states; @buttons; end
      def axes_left; @axes[0,2]; end
      def axes_right; @axes[2,2]; end
      def axes_trigger; @triggers; end
    end
  end
end
module Scancodes
  WIN32 = {A: 65, LBUTTON: 1}
end
def common_keystate(key); $win32KeyStates[key] ? 1 : 0; end
class Win32API
  def initialize(dll, func, *args); @dll = dll; @func = func; end
  def call(*args); :original_api; end
end
$RGSS_SCRIPTS = [[123, 'Battle Bust Config', 'compressed placeholder', 'different script']]
load ARGV.fetch(0)
def assert(value, message); raise message unless value; end
pointer = DL::CPtr.new(DL.malloc(256), 256)
assert($RGSS_SCRIPTS[0][3] == 'different script', 'unrecognized script untouched')
assert(pointer[65] == 0, 'zero-initialized DL allocation')
Input.keys = Array.new(256, false)
Input.keys[65] = true
keyboard = Win32API.new('user32.dll', 'GetKeyboardState', 'I', 'I')
assert(keyboard.call(pointer.to_i) == 1, 'keyboard result')
assert(pointer[65] == 128 && pointer[1] == 128, 'keyboard and native mouse')
assert(pointer[0, 256].bytesize == 256, 'DL slice')
Input.keys[65] = false
keyboard.call(pointer.to_i)
assert(pointer[65] == 0, 'key release and cache refresh')
begin
  pointer[256]
  raise 'out-of-bounds read accepted'
rescue IndexError
end
begin
  keyboard.call(123)
  raise 'unowned pointer accepted'
rescue KeyError
end
begin
  keyboard.call('too short')
  raise 'short buffer accepted'
rescue ArgumentError
end
# Simulate a game that replaces and aliases update. Polling must not recurse.
module Input
  GetKeyboardState = Win32API.new('user32', 'GetKeyboardState', 'I', 'I')
  ToUnicodeEx = Object.new
  class << self
    alias original_game_update update
    def update; GetKeyboardState.call(@test_pointer); end
    alias custom_game_update update
    def update; custom_game_update; end
    def UTF8String; raise 'legacy text method called'; end
    attr_accessor :test_pointer
  end
end
Input.test_pointer = pointer.to_i
Input.characters = "Å漢"
before = Input.updates
Input.update
assert(Input.updates == before + 1, 'native poll once without alias recursion')
assert(Input.UTF8String == "Å漢", 'native UTF-8 text')
assert(Input.UTF8String == '', 'text consumed once')
Input.update
assert(Input.UTF8String == '', 'no stale text')
controller = Input::Controller
controller.connected = true
controller.buttons = Array.new(15, false)
controller.buttons[0] = controller.buttons[11] = true
controller.axes = [0.5, -0.5, -1.0, 1.0]
controller.triggers = [1.0, 0.5]
xinput = Win32API.new('XINPUT1_3', 'XInputGetState', 'IP', 'L')
buffer = "\0" * 16
assert(xinput.call(0, buffer) == 0, 'connected controller')
state = buffer.unpack('VvCCs<s<s<s<')
assert(state[0] > 0 && state[1] == 0x1001, 'XInput button layout')
assert(state[2,2] == [255,128] && state[4,4] == [16384,16384,-32767,-32767], 'axes/triggers')
previous = buffer.dup
xinput.call(0, buffer)
assert(buffer == previous, 'stable packet')
controller.buttons[0] = false
xinput.call(0, buffer)
assert(buffer.unpack('V')[0] != previous.unpack('V')[0], 'packet changes with input')
assert(xinput.call(1, buffer) == 1167, 'second controller unavailable')
controller.connected = false
assert(xinput.call(0, buffer) == 1167, 'disconnection')
assert(Win32API.new('XINPUT1_3','XInputSetState').call(0,buffer) == 50, 'unsupported rumble')
assert(Win32API.new('steam_api','SteamAPI_Init').call == :original_api, 'Steam APIs untouched')
puts 'RGSS_INPUT_COMPAT_PASS'
