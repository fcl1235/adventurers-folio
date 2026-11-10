# adventurers-folio — a D&D **5R** (5.5e / 2024) character sheet

**English** · [简体中文](README.zh-CN.md)

> The repo is `adventurers-folio` (Chinese name **冒险者手帖**, "adventurer's folio" —
> the folder you keep character sheets in). "5R" means the D&D 2024 revision, which the
> community also calls **5.5e** (2014 is plain 5e). This project targets **5R only**;
> it is not a 5e-compatible implementation.

The repo contains **two programs** built on one and the same set of 5R rulings:

| | Old version (finished) | **Rewrite (in progress, `re1` branch)** |
|---|---|---|
| Entry point | `python dnd55e_character_builder.py` (or `启动人物卡.bat`) | `python -m apps.desktop.main` |
| Architecture | `dnd55e/` four-layer monolith, JSON data in the repo root | `dnd5r/` plugin-based engine (content-free kernel) + `apps/` front end + `plugins/` content packs |
| Self-check | `运行自检.bat` (10 steps) | `重构自检.bat` (8 steps: unit tests / layering / plugins / golden diff / layout / layout-in-English / UI text / API text) |
| Docs | `dnd55e_rules_reference.md` | **`架构设计v3-插件化.md`** (design + per-phase build log) |
| Relationship | The two are diffed number by number (a 32,560-entry golden matrix); the old version is the oracle for the new engine | |

The idea behind the rewrite: **the kernel knows no D&D proper nouns** — classes, spells and
monsters are all pluggable content. Layer constraints (C1–C8) and the numeric diff are
enforced by scripts, not by good intentions. The sections below cover the old version first
(it is the one you can simply run); the rewrite lives in the architecture document.

## Quick start (both programs)

Python 3.10+ with tkinter (the official Windows installer includes it).

```
rem --- old version (stable) ---
启动人物卡.bat
python dnd55e_character_builder.py --selftest

rem --- rewrite ---
python -m apps.desktop.main
python -m apps.desktop.main --lang en    # start directly in the English UI
python tools/selfcheck.py        # or double-click 重构自检.bat
python -m apps.cli.main play --level 2   # headless script: build -> use a power -> rest
```

Characters are stored under `characters/` (`_last.json` remembers the last sheet you opened).
Note that the two programs use different save formats (the rewrite goes through `dnd5r.api`
and stores facts only).

### The rewrite's UI (what you see first)

The main window **is** a character sheet: six ability cards on the left (score / modifier /
save), tabbed pages in the middle, combat numbers, the attack table and a dice log on the
right. A hero strip on top holds name, class and level, hit points, and five pills for
AC / initiative / speed / proficiency / passive Perception.

| Page | Contents |
|---|---|
| Overview | Ability cards, skill table, attack table, armour breakdown, combat numbers (AC / initiative / HP / resistances / senses / crit / Hit Dice / exhaustion) |
| Gear | 13 armours (light/medium/heavy/shield) + 38 weapons; one click to swap, and AC plus versatile-weapon damage follow immediately; the left column is a read-only inventory (starting gear and coins included) |
| Spells | Cantrips and spells by level, spell slots, prepare/cast |
| Feats | Choice lists for 67 feats (ability +1, skills, resistances, …) |
| Powers | Class and subclass features, species traits, resource pools |
| Encounter | Initiative order, placing figures, target selection, combat log |
| Status | 14 condition checkboxes + exhaustion 0–6 + death saves + **what you're concentrating on** (with a save DC and an End button); two columns, no scrolling; **short / long rest** at the bottom (spend Hit Dice to heal, refill resources and spell slots) |

The **build wizard** runs inside the main window (no dialogs), in 8 steps: class → background
→ species → ability scores → skills → weapon mastery → spells → summary. Scores support
point buy (27 points) / standard array / roll 4d6 drop lowest, and the inputs constrain
themselves in place (point buy refuses 16; the standard array is a dropdown where picking a
number already taken swaps the two). "Points left" is always visible next to point buy.
Hovering a spell name in the spell step pops its full text (casting time / range /
components / duration / body). Background bonuses are picked from the 7 legal shapes. The
summary step picks **starting equipment** (the 2024 A/B options — e.g. fighter "A: chain mail
+ greatsword + flail + 8 javelins + dungeoneer's pack + 4 gp" / "B: studded leather + scimitar
+ shortsword + longbow + 20 arrows + 11 gp" / "155 gp only"), so the character comes out with
armour worn and weapons already in the attack table instead of a bare AC 10. The
"Edit sheet" button reopens the wizard on this character at any time (feats, multiclass levels
and expertise survive untouched), and "Level up" gains one level while keeping current HP,
inventory and equipment — newly unlocked choices push the wizard straight to that step.

## Rules version: 5R only

Both programs use one standard: the **D&D 2024 revision**. Wherever 5R and 5e differ, 5R wins:

| Area | 5e (2014) | **5R (what this project implements)** |
|---|---|---|
| Source of ability bonuses | Species | **Background** (+2/+1 or +1/+1/+1) |
| Build order | Species → class | **Class → background → species** |
| Fighting styles | Class feature | **Feats** (fighter 1st, paladin/ranger 2nd) |
| Exhaustion | Tiered penalties (disadvantage / half speed / half HP max…) | **Flat d20 −2 and speed −5 ft. per level** |
| Weapon mastery | None | **Weapon Mastery** (each weapon carries one mastery property) |
| Prepared spells | Ability modifier + level | **From the class table** (cantrips, prepared count, pact slots are all looked up) |
| Summon spells | One spell plus one monster stat block | **The Summon line uses standalone stat blocks that scale with slot level** |
| Wild Shape | CR jumps by level/subclass | **4/6/8 known forms, swim at 4th and fly at 8th, moon CR = level ÷ 3** |

5R content is **backwards compatible** with 2014, but this program ships no 2014 data and has
no version switch. (Names like `dnd55e` and `5.5e` in the code are historical; they all mean 5R.)

Feature surface of the old version (the rewrite is catching up phase by phase — see §9 of the
architecture document):

- 12 classes × levels 1–20, 48 subclasses
- 347 spells (including the 8 Summon spells from 2024 and their creatures)
- 140 magic items, 91 beast stat blocks (88 wild-shape forms + 3 ranger companions), 32 summon stat blocks
- 67 feats (43 general + 12 fighting style + 12 epic boon)
- Build wizard + six-tab character sheet + level up / rest / dice

## UI tour (old version)

**Top toolbar**: new character · save · open · export JSON ｜ level up · long rest · short rest ｜ dice tools
**Menus**: `File` (new / save / save as / open save folder / load / export JSON), `Character` (level up / long rest / short rest), `Tools` (dice)
**Shortcuts**: `Ctrl+S` save, `Ctrl+O` open

**Six tabs**

| Tab | Contents |
|---|---|
| Skills | Modifiers for the 18 skills, with proficiency/expertise checkboxes; hover for the description and current bonus |
| Spells | Spell slots, known/prepared lists, spell details (including the summon block), cast/concentration/summon buttons, wizard spellbook |
| Gear & bonuses | Weapons / armour / fighting style / weapon mastery, magic item slots, AC and its sources, resistances/immunities/truesight |
| Class | Resource pools, Hit Dice, sorcery points, metamagic, epic boons, subclass features, Wild Shape, beast companion, subclass, class features |
| Feats & traits | Feat list and text, species traits, background, proficiencies |
| Notes | Languages, equipment list, free-form notes |

**Common interactions**

- Select a spell on the Spells tab → the details pane shows its summon block; spells that summon get a "Summon" button that opens the full stat block card
- Item slots: **left click** to equip/unequip, **right click** for the full effect card (rarity, attunement, full text, numbers already applied, one-click equip from the card)
- Class tab: "spend 1 / regain 1" on resource points, "spend 1 Hit Die to heal", and epic boon ability/resistance/expertise choices all happen in place
- Beast Master from 3rd level gets a "primal companion" panel with three forms and a Beast Strike roll

## Code structure (four layers)

```
dnd55e/
├── core/            domain kernel: the Character itself (imports no UI)
│   ├── base.py       state fields / ability caps / score()
│   ├── derived.py    AC / HP / speed / initiative
│   ├── checks.py     saves / skills / explaining where a bonus comes from
│   ├── combat/       weapon attacks and two-weapon fighting
│   ├── features.py   feat effects / epic boons / companions
│   ├── resources.py  class resource pools
│   └── serialize.py  save/load
├── classes/         one file per class
│   ├── base.py       ClassModule hooks (all no-ops by default)
│   ├── registry.py   @register table (unknown classes fall back to the no-op module)
│   └── barbarian.py … warlock.py
├── spellcasting/    casting, split by caster type and spell level
│   ├── types.py      full / half / third / pact
│   ├── slots.py      spell slots
│   └── levels/       cantrip + level1…level9
├── ui/              presentation: tabs / panels / actions / refresh / classtab
├── dialogs/         dialogs: level up, spellbook, feats, wild shape, summon, item card, dice
├── wizard_steps/    the seven build-wizard steps
├── rules.py         rule-table lookups (read-only JSON)
├── data.py          JSON loader (lru_cache)
├── consts.py        lazily built constants + Chinese copy
├── summoning.py     renders summon blocks
└── wildshape.py     pure functions for beast forms
```

Class rules are no longer scattered through the main program: neither `core/` nor
`spellcasting/` contains a single `class_id == "..."` branch; everything goes through the
`classes.get(class_id)` hooks. **Adding a class = one file in `dnd55e/classes/` plus one
`@register("class_id")` line** — no change to the main program.

## Data files

| File | Contents |
|---|---|
| `dnd55e_core_data.json` | Classes / species / backgrounds / skills / slot tables |
| `dnd55e_classes_detail.json` | Class and subclass features, resource pools |
| `dnd55e_spells.json` | Spells; spells with a `summon` field render a summon block |
| `dnd55e/data/feats_general.json` | 67 feats: 43 general + 12 fighting style + 12 epic boon |
| `dnd55e/data/monsters.json` | 91 beast stat blocks (88 wild-shape forms + 3 ranger companions) |
| `dnd55e/data/summons.json` | 32 summon stat blocks (covering 12 spells) |
| `dnd55e/data/items.json` | 140 magic items |
| `dnd55e/data/fixed_spells.json` | "Always prepared" spells (domain / circle / mastery / signature) |
| `dnd55e/data/metamagic.json` | Metamagic options |

Data comes from SRD 5.2 (the 2024 endpoints of dnd5eapi.co) and public PHB 2024 entries. The
raw scrape snapshots are **not committed** (`data/raw/` is in `.gitignore`); run
`tools/legacy/_fetch_srd.py` if you need them.

## Self-check

```
运行自检.bat
```

10 steps: data health → application self-test → build flow → per-level numeric diff (2,218
items) → layout audit → Chinese/English copy → tooltip clipping → summon validation → module
dependencies → invocation/attack options. It ends with `ALL CHECKS PASSED` when everything is green.

> **After the first clone** `data/raw/` is empty (the directory is not committed, see
> `NOTICE.md`). Step 0 then reports missing data and step 3 prints `SKIP` for the per-level
> diff; the other steps still run. If you want the full diff, run
> `python tools/legacy/_fetch_class_detail.py` and `python tools/legacy/_fetch_srd.py` first to
> fill in the upstream snapshots. **The program itself does not depend on `data/raw/`**;
> building and saving characters works fine.

After editing a data file, run the matching validator (they are not part of the batch file):

```
python tools/legacy/_featcheck.py   # feats_general.json
python tools/legacy/_itemcheck.py   # items.json
python tools/legacy/_moncheck.py    # monsters.json
python tools/legacy/_summoncheck.py # summons.json
```

There are optional deep-verification scripts under `backup/`: `_p2_snapshot.py` +
`_p2_diff.py` (248 numeric snapshots across 12 classes × levels 1–20, needs
`PYTHONHASHSEED=0`), `_p5_tagcheck.py` (checks out every tag into its own worktree and runs
the full self-check), and `_p6a_probe.py` … `_p6f_uiprobe.py` (UI and numeric probes for the
five P6 features).

## Known trade-offs

- **Wild Shape and summons do not replace the character's own numbers**: the program gives you
  the form's or companion's stat block and rolls, while ability scores and HP stay on the
  character, so one transformation cannot corrupt a save file.
- **Ability Score Improvements are added on the Feats page**: from level 4 on (Fighter
  4/6/8/12/14/16, Rogue 4/8/10/12/16, everyone else 4/8/12/16) each of those levels grants
  one allowance; the bottom-left corner of that page says how many are left, and adding one
  takes the +2/+1 in the same step. Levelling into those levels says so in the status line.
  Origin feats still come from a background and Fighting Style from a class feature — those
  cannot be added here, because that would produce a character the rules don't allow.
- **Weapon mastery is resolved**: all eight properties live in `dnd5r/rules/mastery.py`.
  Graze (a miss still deals your ability modifier, resistances apply), Topple (target's
  Constitution save, DC 8 + proficiency + ability, Prone on a failure), Vex and Sap (real
  one-shot advantage / disadvantage marks) are computed on the hit. Cleave, Nick, Push and
  Slow need a second creature, how the weapons are held, or battlefield positions, so the
  program hands you the numbers (second-attack bonus, 10 feet) and says what is missing.
  Only weapons picked when the character was built trigger at all — a `topple` in the item
  data does not mean *you* have it, and the Gear page marks each weapon accordingly.
- **Languages are not modelled**: the sheet does not list languages, and species languages
  (Elvish, Dwarvish, …) are not included — only the ones written into class text such as
  Druidic or Thieves' Cant (G36).
- 63 magic items that "cannot be computed mechanically" (e.g. "cold damage reduction 2d8")
  only show their full text and take no part in the numbers; their `note_only: true` means
  "there are effects beyond the numbers already filled in".
- Some epic boon effects (Energy Transfer, Recovery Pool, …) are recorded as text and not
  resolved automatically.
- **The UI is bilingual (Chinese / English)**: the `EN` / `中文` button in the top bar
  switches language, the choice is stored in `saves/_settings.json` and reused on the
  next start (the system locale only decides the first run).
  Translation has two layers. Text the UI itself writes goes through
  `apps/desktop/i18n.py` (the Chinese original is the key; a missing translation falls back to
  Chinese and is recorded in `MISSING`). **Sentences the rules compute** ("要选 3 项技能，现在选了
  2 项" / "Choose 3 skills; 2 selected") go through `dnd5r/rules/text.py` and must be translated
  *before* formatting — by the time the UI receives them they are a finished sentence with the
  numbers already filled in, so a whole-sentence lookup can never match. Both layers have a
  static audit (`tools/i18n_audit.py` and `--api`), and the layout audit runs a second time in
  English (`tools/uicheck.py --lang en`), because English is not a same-length stand-in for
  Chinese.
  Not translated yet: about 420 engine diagnostics in `dnd5r/rules/` (technical remarks such as
  "why this action is not allowed") are still Chinese; the source marks them with `i18n-keep`
  and states the reason. Content packs (class / spell / feat text) carry both languages and are
  unaffected.

## License and notices

This is **unofficial, free** fan content and is not affiliated with Wizards of the Coast.

- **Program code** (`dnd55e/`, `dnd5r/`, `apps/`, `tools/`, …): MIT License, see `LICENSE`
- **SRD 5.2 rules content**: used under CC-BY-4.0, translated and restructured into Chinese JSON
- **2024 core content outside the SRD**: used under WotC's [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)

Full attribution, list of modifications and disclaimer: **[`NOTICE.md`](NOTICE.md)**.

This repository does **not** contain the raw upstream snapshots in `data/raw/` (excluded via
`.gitignore`); fetch them yourself with `tools/legacy/_fetch_srd.py` if you want them.

> Portions of the materials used are property of Wizards of the Coast LLC. ©Wizards of the Coast LLC.
> This is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards.

## Documents

- `dnd55e_rules_reference.md` — rule baseline and implementation notes (2024 vs 2014 differences, per-item rulings)
- `tools/legacy/_dataspec.md` — field spec for the old version's data (for anyone editing data)
- `架构设计v3-插件化.md` — **the rewrite's design and per-phase build log (read this first)**
- `重构方案.md` — modularisation log for the old program, P1–P5 (done)
- `P6方案.md` — the five P6 features and their results (done)
