using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;

const string SourceHash = "1a1e117add967c0f26ad470a49d4ff442435209265bf1fdda623821d797e80b5";
if (args.Length == 3 && args[0] == "--inspect")
{
    using var inspected = ModuleDefinition.ReadModule(args[1]);
    foreach (var type in AllTypes(inspected.Types))
    foreach (var method in type.Methods.Where(method => method.FullName.Contains(args[2])))
    {
        Console.WriteLine(method.FullName);
        if (method.HasBody) foreach (var instruction in method.Body.Instructions) Console.WriteLine(instruction);
        if (method.HasPInvokeInfo) Console.WriteLine($"Native: {method.PInvokeInfo.Module.Name}!{method.PInvokeInfo.EntryPoint}");
    }
    return;
}
if (args.Length != 4)
    throw new ArgumentException("Expected: source Celeste.exe, FNA.dll, Steamworks.NET.dll, output Celeste.exe");
if (Path.GetFullPath(args[0]) == Path.GetFullPath(args[3]))
    throw new ArgumentException("Output must be a separate copied assembly");
if (Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant() != SourceHash)
    throw new InvalidDataException("Celeste source does not match the audited Steam XNA edition");
using var module = ModuleDefinition.ReadModule(args[0], new ReaderParameters { ReadingMode = ReadingMode.Deferred });
using var fna = ModuleDefinition.ReadModule(args[1]);
using var steam = ModuleDefinition.ReadModule(args[2]);
foreach (var reference in module.AssemblyReferences)
{
    AssemblyNameDefinition? replacement = reference.Name.StartsWith("Microsoft.Xna.Framework") ? fna.Assembly.Name
        : reference.Name == "Steamworks.NET" ? steam.Assembly.Name : null;
    if (replacement == null) continue;
    Console.WriteLine($"Assembly reference: {reference.Name} -> {replacement.FullName}");
    reference.Name = replacement.Name;
    reference.Version = replacement.Version;
    reference.PublicKey = Array.Empty<byte>();
    reference.PublicKeyToken = replacement.PublicKeyToken;
    reference.HasPublicKey = false;
}
foreach (var reference in module.ModuleReferences)
{
    if (reference.Name == "fmod") reference.Name = "libfmod.so.14";
    if (reference.Name == "fmodstudio") reference.Name = "libceleste_fmod_compat.so";
}
foreach (var type in AllTypes(module.Types))
foreach (var method in type.Methods)
{
    if (!method.HasPInvokeInfo) continue;
    var native = method.PInvokeInfo;
    if (native.EntryPoint == "FMOD_Studio_System_SetListenerAttributes")
        native.EntryPoint = "Celeste_FMOD_SetListenerAttributes";
    if (native.EntryPoint == "FMOD_System_Create")
    {
        native.EntryPoint = "Celeste_FMOD_System_Create";
        native.Module = module.ModuleReferences.First(reference => reference.Name == "libceleste_fmod_compat.so");
    }
}
module.Attributes &= ~(ModuleAttributes.Required32Bit | ModuleAttributes.Preferred32Bit);
module.Attributes |= ModuleAttributes.ILOnly;
module.Architecture = TargetArchitecture.I386;
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[3]))!);
module.Write(args[3]);
steam.Attributes &= ~(ModuleAttributes.Required32Bit | ModuleAttributes.Preferred32Bit);
steam.Attributes |= ModuleAttributes.ILOnly;
steam.Architecture = TargetArchitecture.I386;
foreach (var reference in steam.ModuleReferences)
    if (reference.Name is "libsteam_api" or "steam_api" or "steam_api64")
        reference.Name = "steam_api64";
// Initialize the real client interfaces used by this game and the callback
// dispatcher. Newer Frame clients removed unrelated matchmaking/music APIs.
var context = steam.Types.Single(type => type.FullName == "Steamworks.CSteamAPIContext");
var initializeContext = context.Methods.Single(method => method.Name == "Init");
var instructions = initializeContext.Body.Instructions;
foreach (var instruction in instructions)
    if (instruction.OpCode == OpCodes.Ldstr)
        instruction.Operand = instruction.Operand switch {
            "SteamClient020" => "SteamClient023",
            "SteamUser021" => "SteamUser023",
            "STEAMUSERSTATS_INTERFACE_VERSION012" => "STEAMUSERSTATS_INTERFACE_VERSION013",
            _ => instruction.Operand
        };
var appsStore = instructions.Single(instruction => instruction.OpCode == OpCodes.Stsfld
    && instruction.Operand is FieldReference field && field.Name == "m_pSteamApps");
var appsStoreIndex = instructions.IndexOf(appsStore);
var continuation = (Instruction)instructions.Skip(appsStoreIndex).First(instruction => instruction.OpCode == OpCodes.Brfalse_S).Operand;
var cutIndex = instructions.IndexOf(continuation);
while (instructions.Count > cutIndex + 1) instructions.RemoveAt(instructions.Count - 1);
continuation.OpCode = OpCodes.Ldc_I4_1;
continuation.Operand = null;
instructions.Add(Instruction.Create(OpCodes.Ret));
foreach (var handler in initializeContext.Body.ExceptionHandlers.ToArray())
    if (!instructions.Contains(handler.TryStart) || !instructions.Contains(handler.HandlerStart))
        initializeContext.Body.ExceptionHandlers.Remove(handler);
foreach (var type in AllTypes(steam.Types))
foreach (var method in type.Methods)
    if (method.HasPInvokeInfo && method.PInvokeInfo.EntryPoint == "SteamAPI_Init")
        method.PInvokeInfo.EntryPoint = "Celeste_SteamAPI_Init";
steam.Write(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[3]))!, "Steamworks.NET.dll"));
Console.WriteLine("Copied Celeste assembly retargeted to FNA / current Steam wrapper / ARM64 FMOD compatibility library");

static IEnumerable<TypeDefinition> AllTypes(IEnumerable<TypeDefinition> types)
{
    foreach (var type in types)
    {
        yield return type;
        foreach (var nested in AllTypes(type.NestedTypes)) yield return nested;
    }
}
