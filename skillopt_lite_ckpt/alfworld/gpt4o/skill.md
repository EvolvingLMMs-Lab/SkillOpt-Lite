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
| Pick & Place | Put object X in/on receptacle Y | Find X -> `take X N from <src>` -> `go to Y` -> `put X N in/on Y 1` |
| Pick Two & Place | Put two instances of X in/on Y | Find X 1 -> take -> go to Y -> put X 1 in/on Y -> find X 2 -> take -> go to Y -> put X 2 in/on Y |
| Examine in Light | Examine X under desklamp | Find X -> take X -> go to desklamp -> `use desklamp 1` |
| Clean & Place | Clean X then put in Y | Find X -> take X -> `go to sinkbasin 1` -> `clean X N with sinkbasin 1` -> `go to Y` -> `put X N in/on Y 1` |
| Heat & Place | Heat X then put in Y | Find X -> take X -> `go to microwave 1` -> `heat X N with microwave 1` -> `go to Y` -> `put X N in/on Y 1` |
| Cool & Place | Cool X then put in Y | Find X -> take X -> `go to fridge 1` -> `cool X N with fridge 1` -> `go to Y` -> `put X N in/on Y 1` |

**Note on destinations**: Y above is just the final placement receptacle — even when Y is itself an appliance (e.g. `fridge 1`, `microwave 1`, `coffeemachine 1`, `stoveburner 1`, `sinkbasin 1`). The only transformation that applies is the one named in the task type. *Heat & Place into fridge* still means **heat at microwave, then `put` (not `cool`) at fridge**. Once the named transformation is done, your remaining actions must be `go to Y` and `put`.

---

## General Principles

1. **Decompose the task**: Parse the goal into ordered sub-goals (locate, acquire, transform, deliver). Complete each before moving to the next.
2. **Systematic exploration**: Search each surface and container exactly once before revisiting. Open closed containers (drawers, cabinets, fridge) before judging them empty. **Always include the destination receptacle Y in the search** — it is a perfectly valid starting location for the goal object (e.g. a `pot` is often already on `stoveburner`, a `potato` on `diningtable`, a `pen` on a `desk`). Do **not** skip Y just because you plan to place there later. **Kitchen search order (follow this list before opening any `cabinet`/`drawer`)**: (1) all `countertop` instances, (2) all `diningtable` instances, (3) `sinkbasin 1` (cups, mugs, dishware are often here), (4) `coffeemachine 1` (mugs/cups), (5) all `stoveburner` instances (pots, pans, kettles), (6) `fridge 1` (foods, drinks, often cups/mugs/eggs/bowls/lettuce/apple/tomato/potato), (7) `microwave 1` (cooked foods, sometimes dishware), (8) `toaster 1` and `garbagecan 1`, *then* (9) `cabinet` instances, (10) `drawer` instances. Kitchens often have 15+ cabinets — exhausting them first is the #1 way to time-out. **In bathrooms**, scan `countertop`, `toilet`, `sinkbasin`, `handtowelholder`, `towelholder`, `bathtubbasin` before drawers/cabinets. **In bedrooms / living rooms / offices**, scan large open surfaces first (`dresser`, `desk`, `sidetable`, `coffeetable`, `diningtable`, `bed`, `armchair`, `sofa`, `shelf`, `safe` when open) BEFORE the (often numerous) `drawer` and `cabinet` instances — small items like `book`, `newspaper`, `pen`, `keychain`, `remotecontrol`, `cellphone`, `creditcard`, `statue` are usually on these open surfaces.
3. **Grab the right object immediately**: When the goal object (noun matching the task *exactly*) is visible and reachable, take it right away. Do NOT grab any other look-alike object that happens to be on the same surface — it will not satisfy the goal and will block you from carrying the real one (you can only hold one item).
4. **Transform before placing**: If the task requires cleaning, heating, or cooling, perform the state change at the appropriate appliance before heading to the final destination.
5. **Direct delivery**: Once holding the transformed (or untransformed) goal object, navigate straight to the target receptacle and place it.
6. **Track progress**: Maintain an internal count of how many objects still need to be found and placed. Only stop searching when the count reaches zero.
7. **Avoid loops**: Never repeat the same action more than twice in a row. If stuck, move to a different unexplored location.
8. **Only choose admissible actions**: Always pick an action from the admissible action list. Do not invent actions.
9. **Exact object noun**: only `take X N` when `X` matches the goal noun *exactly*. `mug ≠ cup`, `plate ≠ bowl`, `ladle ≠ spatula`, `pot ≠ pan`, `apple ≠ tomato`, `pencil ≠ pen`, `soapbottle ≠ spraybottle`, `soapbar ≠ soapbottle`, `cloth ≠ handtowel`, `tissuebox ≠ toiletpaper`. If the goal says "soapbottle" and the surface has only `spraybottle 1`, keep searching — picking up the wrong object will fail the goal check.

---

## Appliance Protocol (Clean / Heat / Cool)

The transformation is a **single action issued while you are holding the object** and standing at the appliance. The action implicitly opens the appliance, applies the effect, and leaves the object in your inventory.

- **Correct sequence**: `take X N from <src>` -> `go to <appliance> 1` -> `clean X N with sinkbasin 1` (or `heat X N with microwave 1`, `cool X N with fridge 1`) -> `go to <dest>` -> `put X N in/on <dest> 1`.
- **DO NOT** issue `move X N to microwave 1` (or fridge / sinkbasin) before `heat`/`cool`/`clean`. That drops the object inside the appliance and the transformation action then returns `Nothing happens` because you are no longer holding it.
- **DO NOT** manually `open microwave 1` / `close microwave 1` (or fridge) before the heat/cool action. The transformation handles it. Manual open/close only wastes turns.
- After the transformation, the object stays in your hand — go straight to the destination receptacle and use `put X N in/on <dest> N` (not `move`).
- If `heat`/`cool`/`clean` returns `Nothing happens`, you are most likely not holding the object. Check `inventory`; if empty, `take X N from <appliance> 1`, then retry the transformation.
- Only apply the transformation the task requires. Do not cool an object after heating it (or vice versa) — extra transformations can void the goal.
- **Destination ≠ transformation**: if the task is *"heat X and put in fridge"* or *"clean X and put in sinkbasin"*, the fridge/sinkbasin is only the final receptacle. After heating, walk to the fridge and `put X N in/on fridge 1` — do **not** issue `cool X with fridge 1`. Likewise for `clean ... put in microwave` etc.

## Pick Two & Place Protocol

For tasks of the form *"put two X in/on Y"*, you can carry only one instance at a time. The reliable loop is:

1. Find instance 1 -> `take X 1 from <src>` -> `go to Y` -> `put X 1 in/on Y`.
2. Then begin searching for instance 2 -> `take X 2 from <src2>` -> `go to Y` -> `put X 2 in/on Y`.

- **DO NOT** start searching for instance 2 while still holding instance 1. If you try `take X 2 ...` while holding another item, the env returns `Nothing happens` and the turn is wasted.
- Distinct instance numbers (`apple 1`, `apple 2`, ...) refer to physically different objects. Never put the same instance twice.

## Common Mistakes to Avoid

- **Revisiting searched locations**: Keep track of which surfaces/containers have been checked; do not re-examine them.
- **Ignoring visible objects**: If the target object appears in the observation, pick it up immediately.
- **Skipping state changes**: Do not place an object at the destination without first cleaning/heating/cooling it when required.
- **Premature termination**: Do not stop the episode until all goal conditions are verified as met. The action `stop` is **not** valid — never emit it.
- **Action loops**: Repeatedly toggling or examining the same object wastes steps. If the last two actions returned `Nothing happens` or identical feedback, switch to a new location.
- **`Nothing happens` while holding an object** during `clean`/`heat`/`cool`: this usually means the held object is the wrong type for the goal (e.g. you took `handtowel` for a cloth task, or `mug` for a cup task). Put it back (`put X N in/on <current_surface> 1`) and resume searching for the actual goal noun.
- **Search-exhaustion `look` loop**: if you have already scanned the obvious receptacles and still cannot find the goal object, do **not** spam `look` / `examine <appliance>` / `inventory` from one spot — that wastes the remaining turns. Instead: (a) re-check the **destination receptacle** if you haven't, (b) revisit any receptacles you only glanced at (open them if closed), (c) try less-obvious receptacles you skipped (`garbagecan`, `toaster`, `safe`, `armchair`, `sofa`, `bed`, second `sinkbasin`/`fridge` if present). Movement always beats standing still.
