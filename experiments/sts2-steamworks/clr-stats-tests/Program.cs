using System.Reflection;
using System.Reflection.Emit;
using System.Security.Cryptography;

// Execute the candidate's exact IL on the CLR, with tokens rebound to test mocks.
// No game assembly, Steam library, or Steam service is loaded by this harness.
public static class Program
{
    public struct Received { }
    public sealed class Callback
    {
        public required Action<Received> Handler;
        public static Callback Create(Action<Received> handler)
        {
            Registrations++;
            return new Callback { Handler = handler };
        }
    }

    public static bool Initialized, UserReady, GlobalReady, ReadResult, ThrowRead;
    public static long GlobalDamage;
    public static Callback? RetainedCallback;
    public static int Reads, Registrations, DeliveredCallbacks, Refreshes, SafeCalls;
    public static string? ReadName;
    public static bool GetInitialized() => Initialized;
    public static void OnReceived(Received payload) => DeliveredCallbacks++;
    public static bool GetStat(string name, out int value)
    {
        Reads++;
        ReadName = name;
        value = 123;
        if (ThrowRead) throw new IOException("mock read exception");
        return ReadResult;
    }
    public static Task RefreshGlobal()
    {
        Refreshes++;
        return Task.CompletedTask;
    }
    public static Task RunSafely(Task task) { SafeCalls++; return task; }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static Action BindCandidate(string path)
    {
        byte[] assembly = File.ReadAllBytes(path);
        Check(Convert.ToHexString(SHA256.HashData(assembly)).ToLowerInvariant() ==
            "c27aedddd408500ab05ac3c045f41c3f224e3db19c4a6904b5581cc4f588351c", "Wrong candidate hash");
        byte[] code = assembly.AsSpan(356168 + 12, 82).ToArray();
        var method = new DynamicMethod("CandidateInitialize", typeof(void), Type.EmptyTypes, typeof(Program).Module, true);
        DynamicILInfo info = method.GetDynamicILInfo();
        int Method(string name) => info.GetTokenFor(typeof(Program).GetMethod(name)!.MethodHandle);
        int Field(string name) => info.GetTokenFor(typeof(Program).GetField(name)!.FieldHandle);
        var tokens = new Dictionary<int, int>
        {
            [0x06000f34] = Method(nameof(GetInitialized)),
            [0x04000560] = Field(nameof(UserReady)),
            [0x04000561] = Field(nameof(GlobalReady)),
            [0x04000562] = Field(nameof(GlobalDamage)),
            [0x06000f80] = Method(nameof(OnReceived)),
            [0x0a00112f] = info.GetTokenFor(typeof(Action<Received>).GetConstructors()[0].MethodHandle, typeof(Action<Received>).TypeHandle),
            [0x0a001130] = info.GetTokenFor(typeof(Callback).GetMethod(nameof(Callback.Create))!.MethodHandle),
            [0x0400055f] = Field(nameof(RetainedCallback)),
            [0x70004c87] = info.GetTokenFor("architect_damage"),
            [0x0a001132] = Method(nameof(GetStat)),
            [0x06000f7d] = Method(nameof(RefreshGlobal)),
            [0x060077b9] = Method(nameof(RunSafely)),
        };
        var opcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!)
            .ToDictionary(op => unchecked((ushort)op.Value));
        for (int offset = 0; offset < code.Length;)
        {
            ushort opcode = code[offset++];
            if (opcode == 0xfe) opcode = (ushort)(0xfe00 | code[offset++]);
            switch (opcodes[opcode].OperandType)
            {
                case OperandType.InlineNone: break;
                case OperandType.ShortInlineBrTarget:
                case OperandType.ShortInlineVar: offset++; break;
                case OperandType.InlineMethod:
                case OperandType.InlineField:
                case OperandType.InlineString:
                    int token = BitConverter.ToInt32(code, offset);
                    Check(tokens.ContainsKey(token), $"Unexpected token {token:x8}");
                    BitConverter.GetBytes(tokens[token]).CopyTo(code, offset);
                    offset += 4;
                    break;
                default: throw new Exception("Unexpected operand type");
            }
        }
        var locals = SignatureHelper.GetLocalVarSigHelper();
        locals.AddArgument(typeof(int));
        info.SetLocalSignature(locals.GetSignature());
        info.SetCode(code, 2);
        return method.CreateDelegate<Action>();
    }

    private static void Reset()
    {
        Initialized = true;
        UserReady = GlobalReady = true;
        GlobalDamage = 99;
        ReadResult = ThrowRead = false;
        Reads = Registrations = DeliveredCallbacks = Refreshes = SafeCalls = 0;
        ReadName = null;
        RetainedCallback = null;
    }

    public static void Main(string[] args)
    {
        Action initialize = BindCandidate(args[0]);
        int tests = 0;
        Reset(); Initialized = false; initialize();
        Check(Reads == 0 && Registrations == 0 && Refreshes == 0 && UserReady && GlobalReady && GlobalDamage == 99,
            "Uninitialized guard changed state or called Steam"); tests++;
        foreach (bool success in new[] { false, true })
        {
            Reset(); ReadResult = success; initialize();
            Check(UserReady == success && Reads == 1 && ReadName == "architect_damage", "Read result did not control readiness");
            Check(!GlobalReady && GlobalDamage == 0 && Refreshes == 1 && SafeCalls == 1, "Global flow changed");
            Check(Registrations == 1 && RetainedCallback != null && DeliveredCallbacks == 0, "Missing or invented callback");
            Check(RetainedCallback!.Handler.Method == typeof(Program).GetMethod(nameof(OnReceived)), "Wrong retained callback handler");
            tests++;
        }
        Reset(); ThrowRead = true;
        try { initialize(); throw new Exception("Read exception suppressed"); }
        catch (IOException) { }
        Check(!UserReady && Reads == 1 && Registrations == 1 && Refreshes == 0 && DeliveredCallbacks == 0,
            "Exception path invented readiness or callbacks"); tests++;
        Reset(); ReadResult = true; initialize(); ReadResult = false; initialize();
        Check(!UserReady && Reads == 2 && Registrations == 2 && Refreshes == 2 && DeliveredCallbacks == 0,
            "Reinitialization retained stale readiness"); tests++;
        Console.WriteLine($"PASS: {tests} CLR behavior checks on candidate IL; mocked calls only.");
    }
}
