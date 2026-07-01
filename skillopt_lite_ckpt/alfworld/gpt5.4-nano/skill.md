# ALFWorld Embodied Agent Skill

## Overview
This skill guides agents operating in the ALFWorld text-based embodied environment.
The agent must complete household tasks by navigating rooms, interacting with objects,
and using appliances. Actions must be chosen from the admissible action list provided
at each step.

**Output format**: Always output `<think>...</think>` for reasoning, then `<action>...</action>` for the chosen action.

---

## Task Types

| Type | Goal | Key Steps |
|------|------|-----------|
| Pick & Place | Put object X in/on receptacle Y | Find X -> take X -> go to Y -> put X in/on Y |
| Pick Two & Place | Put two instances of X in/on Y | Find X1 -> take X1 -> go to Y -> put X1 in/on Y -> find a DIFFERENT X2 -> take X2 -> go to Y -> put X2 in/on Y |
| Examine in Light | Examine object X under desklamp | Find X -> take X -> `go to desklamp N` -> `use desklamp N` (while still holding X) |
| Clean & Place | Clean object X and put in/on Y | Find X -> take X -> `go to sinkbasin N` -> `clean X with sinkbasin N` -> go to Y -> put X in/on Y |
| Heat & Place | Heat object X and put in/on Y | Find X -> take X -> `go to microwave N` -> `heat X with microwave N` -> go to Y -> put X in/on Y |
| Cool & Place | Cool object X and put in/on Y | Find X -> take X -> `go to fridge N` -> `cool X with fridge N` -> go to Y -> put X in/on Y |

---

## Action Format (strict — copy exactly from admissible list)

| Intent | Format | Example |
|--------|--------|---------|
| Move | `go to <recep> <N>` | `go to countertop 1` |
| Open | `open <recep> <N>` | `open drawer 3` |
| Close | `close <recep> <N>` | `close fridge 1` |
| Take | `take <obj> <N> from <recep> <M>` | `take mug 2 from cabinet 4` |
| Put | `put <obj> <N> in/on <recep> <M>` | `put mug 2 in sinkbasin 1` |
| Move (alias of put) | `move <obj> <N> to <recep> <M>` | `move soapbar 4 to garbagecan 1` |

Note: `put X N in/on Y M` and `move X N to Y M` are **both** valid delivery actions — either one satisfies the goal when X N lands on the target receptacle. Use whichever appears in the current admissible list; if both are listed, pick `put`. **A single successful placement (either verb) completes the delivery sub-goal for that instance.** Never re-place the same instance — once you see "You put/move the X N to the Y", that half-goal is DONE.
| Clean | `clean <obj> <N> with sinkbasin <M>` | `clean fork 1 with sinkbasin 1` |
| Heat | `heat <obj> <N> with microwave <M>` | `heat egg 1 with microwave 1` |
| Cool | `cool <obj> <N> with fridge <M>` | `cool bread 1 with fridge 1` |
| Use light | `use <desklamp> <N>` | `use desklamp 1` |

Never emit prose actions ("I'll grab the apple"). Never invent receptacle indices — use only the ones in the current admissible action list or that have appeared in observations. If the action you want isn't admissible right now, you are probably not at the right receptacle — `go to` it first.

### ⚠️ Verb-noun match — CRITICAL

The object you `take` must match the noun in the task description. If the goal says "heat some **mug**", you must `take mug N`, not `take cup N`. Cup, mug, bowl, plate, pot, pan are all distinct nouns to the goal checker — do not substitute even if they look similar. Re-read the task verbatim before each `take`.

---

## Where Common Objects Usually Live (search these FIRST)

If the target object is not visible after a brief look, prioritise these high-yield receptacles before falling back to a full sweep:

| Object family | Likely receptacles |
|---------------|--------------------|
| AlarmClock, CellPhone, KeyChain, Watch, CreditCard, Pen, Pencil, Book, CD, Laptop, RemoteControl, Statue, Vase | desk, sidetable, dresser, shelf, drawer, coffeetable, sofa, bed, armchair |
| Newspaper, TissueBox, Box, Pillow, Cloth, Pen, Pencil | sofa, coffeetable, sidetable, armchair, bed, dresser, drawer, ottoman |
| Mug, Cup, Bowl, Plate, Pan, Pot, Kettle, Fork, Knife, Spoon, ButterKnife, Spatula, Ladle, Egg, Apple, Tomato, Lettuce, Potato, Bread, WineBottle | countertop, diningtable, cabinet, drawer, fridge, sinkbasin, microwave, stoveburner, shelf |
| SoapBar, SoapBottle, SprayBottle, ToiletPaper, Candle, DishSponge, Towel, HandTowel | countertop, cabinet, drawer, toilet, sinkbasin, shelf, garbagecan, bathtubbasin, cart, towelholder |
| DeskLamp, FloorLamp | desk, sidetable, dresser, shelf (lamps are usually at fixed locations — note them when seen) |

When the room has many cabinets/drawers/shelves indexed 1..K, sweep them in order but **stop the moment the target appears**. If the first 4–5 of a kind are empty, switch to other receptacle types instead of exhausting all of them.

---

## General Principles

1. **Decompose the task**: Parse the goal into ordered sub-goals (locate, acquire, transform, deliver). Complete each before moving to the next.
2. **Systematic exploration**: Search each surface and container **at most once** before moving on. Open closed containers (drawers, cabinets, fridge) on the first visit; do not re-open or re-examine the same one. Track a mental list of receptacles already checked.
3. **Grab immediately**: When a required object is visible (mentioned in the current observation), `take <obj> <N> from <recep> <M>` on the very next action. Do not `examine` it — examining never changes state.
4. **Transform before placing**: If the task requires cleaning, heating, or cooling, perform the state change at the appliance **while holding the object**, then walk straight to the destination receptacle and place it.
5. **Direct delivery**: Once holding the transformed (or untransformed) goal object, navigate straight to the target receptacle and place it. No detours, no extra examines.
6. **Track progress**: Maintain an internal count of how many objects still need to be found and placed. For Pick Two, you need TWO distinct instances — after putting the first, the second must be a different `<obj> <N>` (different index) or one that appeared after the first was placed.
7. **Avoid loops**: Never repeat the same action twice. If the last action returned "Nothing happens" or you see the same observation twice, switch to a brand-new receptacle on the next turn. **Hard rule**: if by turn 15 you have not yet `take`n the target object, you MUST visit a receptacle TYPE you have not yet visited — e.g. if you've only looked in fridge/countertop/cabinet/drawer, your next `go to` must be one of `diningtable`, `sidetable`, `coffeetable`, `desk`, `dresser`, `sofa`, `shelf`, `stoveburner`, `microwave`, `garbagecan`, `toilet`, `bathtubbasin`, `cart`, `bed`, `armchair`, `ottoman`, `safe`, `toiletpaperhanger` — whichever exists in the room and you have NOT yet visited. Kitchen produce (tomato, lettuce, apple, potato, egg, bread) very often spawns on `diningtable`, not just countertop/fridge.
8. **Only choose admissible actions**: Always pick an action from the admissible action list. Do not invent actions or fabricate receptacle indices.
9. **Budget your turns**: You have at most 50 turns. By turn 25 you should be holding the target object (or have located both for Pick Two). By turn 40 the state change should be done. Spend the final turns on delivery, not on more searching.

---

## Worked example (use this exact verb pattern)

Task: *put two saltshaker in drawer.* Correct ending sequence after locating both saltshakers:

```
take saltshaker 4 from countertop 3   -> You pick up the saltshaker 4 from the countertop 3.
go to drawer 1                        -> ...the drawer 1 is open. In it, you see nothing.
put saltshaker 4 in drawer 1          -> You put the saltshaker 4 in/on the drawer 1.   <-- this is what ends the half-goal
go to countertop 1                    -> ...you see a saltshaker 2, ...
take saltshaker 2 from countertop 1   -> You pick up the saltshaker 2 from the countertop 1.
go to drawer 1                        -> ...the drawer 1 is open. In it, you see a saltshaker 4.
put saltshaker 2 in drawer 1          -> You put the saltshaker 2 in/on the drawer 1.   <-- second put ends the episode
```

Note: a delivery action is either `put X N in/on Y M` OR `move X N to Y M` — both work and either ends the half-goal when X N actually lands on Y M. **One successful placement per instance is enough.** After you see "You put/move the X N to the Y", DO NOT re-take or re-place X N — that half-goal is already credited. For Pick-Two, instead go and find a DIFFERENT instance `X K` (different numeric index) and place that one too.

## Recipe Details (do these exactly)

### Examine in Light (look_at_obj_in_light)
1. **Spot the desklamp first.** As you sweep the room, the moment any observation mentions `desklamp <N>` (or `floorlamp <N>`), memorise that receptacle — that is your delivery destination.
2. Locate target object X. `take X N from <recep>`.
3. `go to desklamp M` (or floorlamp). **Do not** issue `look`, `examine X`, or `examine <recep>` after taking — those never satisfy the goal and they are the #1 source of timeout on this task type. (Don't place the object either — you need to be holding it when you `use`.)
4. `use desklamp M`. This succeeds as long as you are at the lamp and holding X. One `use` is enough — episode ends on success. If `use desklamp` is not admissible, you are not at the lamp yet — `go to desklamp M` again.
5. If the lamp index hasn't shown up after sweeping desks / sidetables / shelves / dressers, switch to those receptacle types specifically (lamps live there).

### Pick Two & Place (pick_two_obj_and_place)

**Goal completion needs TWO DISTINCT instances** of X delivered to the target receptacle — e.g. `cup 1` AND `cup 2`, or `alarmclock 2` AND `alarmclock 3`. Re-placing the same instance counts as one and will NEVER complete the goal no matter how many times you repeat.

1. Find first X instance (X_a). `take X_a from <recep>`.
2. `go to <target_recep>`. Then `put X_a in/on <target_recep>` (or `move X_a to <target_recep>` if `put` isn't admissible — both work). Use `in` for containers (cabinet, drawer, fridge, box, garbagecan), `on` for surfaces (bed, desk, sidetable, dresser, countertop, diningtable, shelf, sofa, coffeetable, armchair, ottoman). If one preposition triggers "Nothing happens", try the other immediately.
3. **STOP. Look at your inventory — it should be empty now. The first half-goal is DONE.** Now go find a SECOND, different instance (X_b with a different numeric index than X_a). If X_b isn't visible, sweep cabinets / drawers / shelves you haven't opened, plus typical second-spawn locations (countertop, sidetable, desk, dresser, sofa, coffeetable, bed). **Never re-take or re-place X_a** — if `cup 1` is now on the target, look for `cup 2`, `cup 3`, etc. If you've placed X_a and your next action is `take X_a from <target>` or `put X_a ...` again, you are in the failure loop — instead `go to` an unsearched receptacle.
4. `take X_b from <recep>`. `go to <target_recep>`. `put X_b in/on <target_recep>` (or `move X_b to <target_recep>`).
5. If after placing X_a you see another `X N` already on the target receptacle in the new observation, take that one next.

### Clean / Heat / Cool & Place
1. Take the object.
2. Go to the appliance (`sinkbasin` / `microwave` / `fridge`).
3. Issue `clean X N with sinkbasin M` / `heat X N with microwave M` / `cool X N with fridge M`. You do **not** need to manually `open` the microwave/fridge for the clean/heat/cool action — the verb handles it. **One** such call is sufficient — do NOT repeat it.
4. Go directly to the target receptacle. `put X N in/on <target_recep>` (or `move X N to <target_recep>` if `put` is not admissible). One placement is enough — do not loop. If the FB says "You put/move the X N to the Y" and the episode doesn't end immediately, you are likely missing a step (e.g. forgot to clean/heat/cool first, or wrong receptacle). DO NOT re-take and re-place X N — instead, check whether you skipped the transform step or whether you delivered to the wrong receptacle.

---

## Common Mistakes to Avoid

- **Re-placing the same instance**: ONE placement per instance is enough. After you see "You put/move the X N to the Y", that delivery is credited — do NOT `take X N` from the target and `put` it again. The fix for Pick-Two if you're stuck on the second instance is to GO SEARCH for a different `X K` (different index), not to keep re-placing `X N`.
- **Revisiting searched locations**: Keep track of which surfaces/containers have been checked; do not re-examine them. `examine drawer 2` after you just opened it is wasted. After 3 failed visits to the same area, change receptacle TYPE (not just index): if cabinets 1-4 are empty and the target is a small movable item, leave cabinets and try desks / sidetables / drawers / dressers / shelves.
- **`look` / `examine` loops**: `look` repeated more than once in a row, or `examine X` after `take X`, never changes state. If you've already emitted `look` or `examine X` and the situation didn't change, switch to `go to <new receptacle>`.
- **Wrong-object substitution**: If you took the wrong object (e.g. `cup 1` when the task wanted `mug`), `put` it back on the nearest receptacle and resume searching for the correct noun. Don't keep transforming and placing the wrong item.
- **Examining instead of taking**: When the observation lists `<target>` on a receptacle, the very next action MUST be `take <target> <N> from <recep> <M>`. Never `examine <target>` — it returns "nothing special" and burns a turn.
- **`examine <recep>` after `open <recep>`**: `open` already prints the contents. Skip the redundant `examine`.
- **Re-toggling lamps**: `use desklamp` once is enough; don't toggle it on/off repeatedly. If the task is Examine-in-Light and you are holding the target, one `use desklamp N` ends the task.
- **Repeating `look`**: `look` returns the same info each turn; use it at most once.
- **Skipping state changes**: Do not place an object at the destination without first cleaning/heating/cooling it when required.
- **Pick Two duplicate-instance trap**: After putting `X 1` on the target, do not try to `take X 1` again — that exact instance is now placed. Find a different index (`X 2`, `X 3`, ...).
- **Searching only one receptacle family**: If the target is a CreditCard / Newspaper / AlarmClock, do not exhaust all 8 drawers before checking desk / sidetable / sofa / coffeetable. Use the location table above.
- **Action loops**: Repeatedly toggling or examining the same object wastes steps. After "Nothing happens" or two identical observations in a row, pick a brand new receptacle.
- **Premature termination**: Do not stop the episode until all goal conditions are verified as met.
