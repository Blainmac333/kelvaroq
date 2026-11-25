using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;

namespace Kelvaroq {
internal static class Checks {
    static void Check(bool ok) { if (!ok) throw new InvalidOperationException("Assertion failed"); }
    static void Reject(Action action) {
        try { action(); } catch (Exception ex) {
            if (ex is Problem || ex is InvalidDataException || ex is IOException || ex is ArgumentException) return;
            throw;
        }
        throw new InvalidOperationException("Unexpected success");
    }
    internal static void Run(string suite,string root) {
        string home = Path.Combine(root,"preferences"), history = Path.Combine(home,"snapshots");
        var p = new Preferences { data = Path.Combine(root,"data"), cache = Path.Combine(root,"cache") };
        Directory.CreateDirectory(home);
        switch (suite) {
            case "language":
                var english = new Locale("en").Strings;
                foreach (string code in Locale.Codes) {
                    var table = new Locale(code).Strings;
                    Check(table.Count == english.Count && english.Keys.All(k => table.ContainsKey(k) && !String.IsNullOrWhiteSpace(table[k])));
                    foreach (var key in english.Keys) foreach (var placeholder in new[]{"{0}","{1}"})
                        Check(english[key].Contains(placeholder) == table[key].Contains(placeholder));
                }
                Check(new Locale("fr-CA").Code == "fr"); Check(new Locale("pt-PT").Code == "pt-BR"); break;
            case "settings":
                p.Write(home); var file = Path.Combine(home,"settings");
                var json = Files.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(file));
                json["schema_version"] = 1; json.Remove("days"); json.Remove("recent");
                File.WriteAllText(file,Files.Json.Serialize(json));
                var migrated = Preferences.Load(home);
                Check(migrated.schema_version == 2 && migrated.days == 14 && migrated.recent == 8 && migrated.data == p.data);
                Check(Preferences.Load(home).schema_version == 2);
                json["schema_version"] = 17; File.WriteAllText(file,Files.Json.Serialize(json)); Reject(() => Preferences.Load(home));
                p.cache = p.data; Reject(() => p.Write(home)); break;
            case "paths":
                string config = Path.Combine(root,"MicrosoftGame.Config"), exe = Path.Combine(root,"bin","sample.exe");
                Directory.CreateDirectory(Path.GetDirectoryName(exe)); File.WriteAllBytes(exe,new byte[0]);
                Reject(() => Installation.Select(exe)); Reject(() => Installation.Select(root));
                File.WriteAllText(config,"<Game><ExecutableList><!-- <Executable Name='ignored.exe'/> --><Executable Name='bin/sample.exe' TargetDeviceFamily='Scarlett'/></ExecutableList></Game>",Encoding.Unicode);
                Check(Installation.Select(root).Image == exe); Check(Installation.Select(exe).Root == root);
                var other = Path.Combine(root,"other.exe"); File.WriteAllText(other,""); Reject(() => Installation.Select(other));
                File.WriteAllText(config,"<Game><ExecutableList><Executable Name='../outside.exe'/></ExecutableList></Game>"); Reject(() => Installation.Select(root));
                File.WriteAllText(config,"<"); Reject(() => Installation.Select(root)); break;
            case "retention":
                DateTime now = new DateTime(2026,11,10,16,0,0,DateTimeKind.Utc);
                var samples = new[]{0,1,2,24,25,48,72}.Select(h => new Snapshot { Info = new Manifest { created_at = now.AddHours(-h).ToString("o") } }).ToList();
                Check(Archives.Expired(samples,now,2,3).SequenceEqual(new[]{samples[2],samples[4],samples[6]}));
                Check(Archives.Expired(samples,now,1,0).Count() == 6); break;
            case "move":
                Directory.CreateDirectory(p.cache); File.WriteAllText(Path.Combine(p.cache,"one"),"original");
                var dest = Path.Combine(root,"target");
                Reject(() => Relocation.Move(p.cache,dest,n => {},delegate { throw new IOException(); }));
                Check(!Directory.Exists(dest) && Files.Size(p.cache) == 8);
                Reject(() => Relocation.Move(p.cache,dest,n => {},useNew => {
                    if (useNew) File.WriteAllText(Path.Combine(p.cache,"changed"),"new");
                }));
                Check(!Directory.Exists(dest) && File.Exists(Path.Combine(p.cache,"changed")));
                int last = 0; Relocation.Move(p.cache,dest,n => last = n,delegate {});
                Check(last == 100 && !Directory.Exists(p.cache) && File.ReadAllText(Path.Combine(dest,"one")) == "original"); break;
            case "clear":
                foreach (var name in new[]{"shaders","pipelines"}) {
                    var dir = Path.Combine(p.cache,name); Directory.CreateDirectory(dir); File.WriteAllText(Path.Combine(dir,"entry"),"cache");
                }
                Files.ClearShaders(p.cache); Check(!Directory.Exists(Path.Combine(p.cache,"shaders")) && Files.Size(p.cache) == 5);
                Directory.CreateDirectory(p.data); File.WriteAllText(Path.Combine(p.data,"slot"),"saved");
                Archives.ClearData(p,history,"def"); Check(Files.Size(p.data) == 0);
                Archives.Restore(Archives.History(history).Single().Path,p,history,"def");
                Check(File.ReadAllText(Path.Combine(p.data,"slot")) == "saved");
                break;
            case "options":
                var info = new System.Diagnostics.ProcessStartInfo { UseShellExecute = false };
                var game = new Installation { Image = Path.Combine(root,"bin","sample.exe"), Root = root };
                p.monitor = true; p.preload = false;
                Product.Configure(info,game,p,new Locale("en"),true);
                Check(info.EnvironmentVariables["VICTORY_GAME_DIR"] == root && info.EnvironmentVariables["VICTORY_CACHE_DIR"] == p.cache &&
                    info.EnvironmentVariables["VICTORY_DATA_DIR"] == p.data && info.EnvironmentVariables["VICTORY_PIPELINE_PRECOMPILE"] == "0" &&
                    info.EnvironmentVariables["VICTORY_LAUNCHER_MONITOR"] == "1" && info.EnvironmentVariables["VICTORY_STATS_SHM"] == "1");
                break;
            case "session":
                Directory.CreateDirectory(p.data);
                string state = Path.Combine(p.data,"slot");
                File.WriteAllText(state,"before");
                Check(Session.Run(p,history,"abc",true,delegate {
                    Check(Archives.History(history).Single().Info.reason == "beforeLaunch");
                    File.WriteAllText(state,"after"); return 0;
                }) == 0);
                Check(Archives.History(history).Count == 2 && Archives.History(history)[0].Info.reason == "afterExit");
                Check(Session.Run(p,history,"abc",true,delegate { return 2; }) == 2);
                Check(Archives.History(history).Count == 3);
                Session.Run(p,history,"abc",false,delegate { return 0; });
                Check(Archives.History(history).Count == 3);
                break;
            case "recovery":
                Directory.CreateDirectory(history);
                var token = Guid.NewGuid().ToString("N");
                var prefix = Path.Combine(root,".kelvaroq-" + token);
                Directory.CreateDirectory(prefix + ".previous");
                File.WriteAllText(Path.Combine(prefix + ".previous","save"),"last good");
                Directory.CreateDirectory(prefix + ".incoming");
                File.WriteAllText(Path.Combine(history,"replacement.json"),Files.Json.Serialize(new Archives.Replacement { token = token, destination = p.data }));
                Archives.Recover(p.data,history); Archives.Recover(p.data,history);
                Check(File.ReadAllText(Path.Combine(p.data,"save")) == "last good" && !Directory.Exists(prefix + ".incoming"));
                break;
            case "archive":
                Directory.CreateDirectory(Path.Combine(p.data,"empty")); string save = Path.Combine(p.data,"save");
                File.WriteAllText(save,"first");
                string snapshot = Archives.Write(p.data,history,"abc","manual","sample");
                string export = Path.Combine(root,"export.zip"); Archives.Export(snapshot,export);
                File.WriteAllText(save,"second"); Archives.Restore(export,p,history,"def");
                Check(File.ReadAllText(save) == "first" && Directory.Exists(Path.Combine(p.data,"empty")));
                var backup = Archives.History(history).Single(s => s.Info.reason == "beforeRestore");
                Archives.Restore(backup.Path,p,history,"def"); Check(File.ReadAllText(save) == "second");
                foreach (string fault in new[]{"version","checksum","traversal","missing","corrupt"}) {
                    var damaged = Path.Combine(root,fault + ".zip"); File.Copy(export,damaged);
                    if (fault == "corrupt") File.WriteAllText(damaged,"invalid");
                    else using (var stream = File.Open(damaged,FileMode.Open)) using (var zip = new ZipArchive(stream,ZipArchiveMode.Update)) {
                        var e = zip.GetEntry("manifest.json"); Manifest m;
                        using (var r = new StreamReader(e.Open())) m = Files.Json.Deserialize<Manifest>(r.ReadToEnd());
                        e.Delete();
                        if (fault == "version") m.format_version = 0;
                        if (fault == "checksum") m.files[0].sha256 = new string('0',64);
                        if (fault == "traversal") m.files[0].path = "../escape";
                        if (fault != "missing") using (var w = new StreamWriter(zip.CreateEntry("manifest.json").Open())) w.Write(Files.Json.Serialize(m));
                    }
                    Reject(() => Archives.Restore(damaged,p,history,"def"));
                    Check(File.ReadAllText(save) == "second" && !File.Exists(Path.Combine(root,"escape")));
                }
                break;
            default: throw new ArgumentException(suite);
        }
    }
}
}
