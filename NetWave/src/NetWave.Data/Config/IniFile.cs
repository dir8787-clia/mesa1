using System.Globalization;
using System.Text;

namespace NetWave.Data.Config;

/// <summary>
/// Простейший INI-парсер/писатель (UTF-8, разделы [Section], ключ = значение).
/// </summary>
public sealed class IniFile
{
    private readonly Dictionary<string, Dictionary<string, string>> _sections =
        new(StringComparer.OrdinalIgnoreCase);

    public IReadOnlyDictionary<string, Dictionary<string, string>> Sections => _sections;

    public static IniFile Load(string path)
    {
        var ini = new IniFile();
        if (!File.Exists(path)) return ini;
        var current = "Default";
        foreach (var raw in File.ReadAllLines(path))
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith(';') || line.StartsWith('#')) continue;
            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                current = line[1..^1].Trim();
                if (!_sections.ContainsKey(current))
                    _sections[current] = new(StringComparer.OrdinalIgnoreCase);
                continue;
            }
            var eq = line.IndexOf('=');
            if (eq <= 0) continue;
            if (!_sections.TryGetValue(current, out var dict))
                _sections[current] = dict = new(StringComparer.OrdinalIgnoreCase);
            dict[line[..eq].Trim()] = line[(eq + 1)..].Trim();
        }
        return ini;
    }

    public string GetString(string section, string key, string def = "")
        => _sections.TryGetValue(section, out var s) && s.TryGetValue(key, out var v) ? v : def;

    public int GetInt(string section, string key, int def = 0)
        => int.TryParse(GetString(section, key, ""), NumberStyles.Integer,
                        CultureInfo.InvariantCulture, out var v) ? v : def;

    public bool GetBool(string section, string key, bool def = false)
    {
        var raw = GetString(section, key, "");
        if (raw.Length == 0) return def;
        return raw is "1" or "true" or "yes" or "on";
    }

    public void Set(string section, string key, string value)
    {
        if (!_sections.TryGetValue(section, out var s))
            _sections[section] = s = new(StringComparer.OrdinalIgnoreCase);
        s[key] = value;
    }

    public void Set(string section, string key, int value)
        => Set(section, key, value.ToString(CultureInfo.InvariantCulture));

    public void Set(string section, string key, bool value) => Set(section, key, value ? "1" : "0");

    public void Save(string path)
    {
        var sb = new StringBuilder();
        foreach (var (section, kv) in _sections)
        {
            sb.Append('[').Append(section).Append("]\n");
            foreach (var (k, v) in kv)
                sb.Append(k).Append(" = ").Append(v).Append('\n');
            sb.Append('\n');
        }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path, sb.ToString(), Encoding.UTF8);
    }
}
