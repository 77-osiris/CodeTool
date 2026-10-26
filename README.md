# CodeTool

Extract, format and output values from a list. Paste or load a list, pick which part of each line you want, choose how to format it, then copy or save the result.

```
0000000000-UC01      ->  0000000000
ABC123  Some Name    ->  ABC123
```

Works as a desktop GUI or from the command line, using the same engine.

## Requirements

- Python 3.7+
- tkinter (included with the standard Windows Python installer), needed for the GUI only
- Optional: `pyperclip` for clipboard output from the command line on macOS/Linux

No other dependencies.

## GUI

Double-click `codetool.py`, or run:

```
python codetool.py
```

Rename it to `codetool.pyw` to open without a console window.

The window has three panes: **Input**, **Options** and **Output**. The output updates as you type or change options.

1. **Extract**: delimiter, part, optional regex, digits only, remove duplicates, sort A–Z
2. **Format**: preset, quote, prefix, suffix, join text, wrap, join after last value
3. **Output**: copy to clipboard, or save as `.txt`, `.sql` or `.csv` in UTF-8 or cp1252

| Shortcut | Action |
|---|---|
| Ctrl+O | Open file |
| Ctrl+Enter | Copy output |
| Ctrl+S | Save output |
| Ctrl+A | Select all in the focused pane |

Settings, the last folder used and the window size are saved to `~/.codetool.json` when you close the window. Input text is never saved.

## Command line

```
python codetool.py stus.txt                            # 1st whitespace column, to screen
python codetool.py stus.txt -d - --digits              # 0000000000-UC01 -> 0000000000
python codetool.py stus.txt -d middot -p 1             # part after the middle dot
python codetool.py stus.txt --preset sits --out clip   # A·|B·|C  -> clipboard
python codetool.py stus.txt --preset sql -o codes.txt  # 'A',\n'B'  -> file
python codetool.py stus.txt --preset sql-in            # ('A', 'B', 'C')
```

Omit the input file to read from stdin. Use `--gui` to open the GUI explicitly, and `-h` for full help.

### Extraction

| Option | Description |
|---|---|
| `-d`, `--delimiter` | Default is whitespace. Accepts a literal (`-`, `"|"`), a name (`middot`, `pipe`, `tab`, `space`, `comma`, `semicolon`, `dash`, `underscore`, `colon`, `slash`, `bullet`, `dot`) or a code (`U+00B7`, `\u00b7`, `0xB7`) |
| `-p`, `--part` | `0` = first piece (default), `1` = second, `-1` = last |
| `--digits` | Keep digits only |
| `--regex` | Use a regex instead of delimiter/part; the first capture group is used |
| `--unique` | Drop duplicates, keeping the original order |
| `--sort` | Sort A–Z |

Blank lines and leading list bullets (`- `, `* `, `• `) are skipped automatically.

### Formatting

| Option | Description |
|---|---|
| `--prefix`, `--suffix`, `--quote` | Added to each value |
| `--join` | Text between values (default newline). Supports `\n`, `\t`, `\uXXXX` |
| `--trailing` | Also add the join text after the last value |
| `--wrap OPEN CLOSE` | Text around the whole result, e.g. `"(" ")"` |
| `--preset` | Starting format; explicit options override it |

### Presets

| Preset | Output |
|---|---|
| `lines` | One value per line (default) |
| `sits` | `A·|B·|C` |
| `sql` | `'A',` / `'B'` on separate lines |
| `sql-in` | `('A', 'B', 'C')` |
| `csv` | `A,B,C` |

### Output

| Option | Description |
|---|---|
| `--out screen\|file\|clip` | Where to send the result (default `screen`) |
| `-o FILE` | Write to a file |
| `--out-encoding` | `utf-8` (default) or `cp1252` |
| `--encoding` | Force the input encoding (`utf-8`, `cp1252`, `utf-16`). By default it detects UTF-8 (with or without BOM) and UTF-16, then falls back to cp1252 |
