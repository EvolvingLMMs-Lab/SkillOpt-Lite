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
| Pick & Place | Put object X in/on receptacle Y | Find X -> `take X from <src>` -> `go to Y` -> `put X in/on Y` |
| Pick Two & Place | Put two instances of X in/on Y | Find X1 -> take -> `go to Y` -> `put X1 in/on Y` -> find a DIFFERENT instance X2 -> take -> `go to Y` -> `put X2 in/on Y` |
| Examine in Light | Examine object X under desklamp | Find X -> take X -> `go to <desklamp>` -> `use desklamp 1` (do NOT take the lamp) |
| Clean & Place | Clean object X and put in/on Y | Find X -> take X -> `go to sinkbasin 1` -> `clean X with sinkbasin 1` -> `go to Y` -> `put X in/on Y` |
| Heat & Place | Heat object X and put in/on Y | Find X -> take X -> `go to microwave 1` -> `heat X with microwave 1` -> `go to Y` -> `put X in/on Y` |
| Cool & Place | Cool object X and put in/on Y | Find X -> take X -> `go to fridge 1` -> `cool X with fridge 1` -> `go to Y` -> `put X in/on Y` |

**Transform appliance is fixed by the verb, not the destination**: heat ->
microwave, cool -> fridge, clean -> sinkbasin. The receptacle named in
"put ... in/on Y" (e.g. "put a cool tomato in **microwave**", "heat egg and
put it in **fridge**") is the DELIVERY target — you `put` the object there;
you do NOT transform it there. So for "put a cool tomato in microwave":
cool at the fridge first, then `put tomato in/on microwave 1`.

---

## Appliance Interaction Protocol (Heat / Cool / Clean)

State changes are a SINGLE atomic command issued while you are **holding the
object** and standing at the appliance. You do NOT open the appliance, move
the object inside, toggle the door, or examine it:

- Heat:  `heat <obj> with microwave 1`
- Cool:  `cool <obj> with fridge 1`
- Clean: `clean <obj> with sinkbasin 1`

Correct sequence (e.g. heat): `take plate 1 from shelf 2` -> `go to
microwave 1` -> `heat plate 1 with microwave 1`. That one `heat` command
fully heats the plate even if the microwave is closed — there is no need to
`open microwave 1`, `move plate 1 to microwave 1`, or `close microwave 1`.

**Never** enter an open/close/move/examine loop on an appliance. If you
catch yourself issuing `move X to microwave`, `open microwave`, or
`examine microwave` to try to heat something, STOP and instead issue the
single `heat X with microwave 1` command while holding X. The same applies
to fridge (`cool`) and sinkbasin (`clean`).

After the transform, go straight to the delivery receptacle and `put X
in/on Y`.

---

## General Principles

1. **Match the EXACT object noun — `cup` ≠ `mug`**: The target is the precise noun in the task. `cup`, `mug`, `glass`, `bowl`, `pot`, and `pan` are DISTINCT object types — never substitute one for another. If the task says "cool some **cup**", you must `take cup N` — taking a `mug` instead silently fails the whole task even if you cool and place it correctly. If the first surface only has a `mug` and you need a `cup`, keep searching other locations until the exact-noun instance appears; the environment guarantees at least one exists. Same for any near-synonym pair.
2. **Decompose the task**: Parse the goal into ordered sub-goals (locate, acquire, transform, deliver). Complete each before moving to the next.
2. **Search likely open locations first**: Plates, pots, pans, bread, mugs, and similar items usually sit on open surfaces — check `countertop`, `diningtable`, `shelf`, `sinkbasin`, `stoveburner`, the `coffeemachine`/`garbagecan`, and the destination receptacle itself (the target object often already sits on/in it) before exhaustively opening every closed cabinet/drawer. Only open closed containers (drawers, cabinets, fridge) after these open surfaces don't have the object. This avoids burning 30+ steps opening empty cabinets.
3. **Grab immediately**: When a required object is visible and reachable, take it right away before moving elsewhere.
4. **Transform before placing**: If the task requires cleaning, heating, or cooling, perform the state change at the appropriate appliance before heading to the final destination.
5. **Direct delivery — you must be AT the receptacle to place**: `put`/`move X in/on Y` only succeeds while you are standing at Y. ALWAYS issue `go to Y` immediately before the `put`/`move`, even if you visited Y earlier or just transformed the object elsewhere. If a `put`/`move` returns "Nothing happens", you are not at the receptacle (or not holding the object) — `go to Y` first, then retry the `put`/`move`.
6. **Track progress**: Maintain an internal count of how many objects still need to be found and placed. Only stop searching when the count reaches zero.
7. **Avoid loops**: Never repeat the same action more than twice in a row. If stuck, move to a different unexplored location.
8. **Only choose admissible actions**: Always pick an action from the admissible action list. Do not invent actions.

---

## Common Mistakes to Avoid

- **Wrong object type (`cup` vs `mug`, `bowl` vs `pot`, etc.)**: Grabbing a near-synonym object instead of the exact noun named in the task fails the task even after a correct transform + place. Before `take`, confirm the object name matches the task noun character-for-character (ignoring the instance number). If it doesn't, keep searching.
- **`put`/`move` from the wrong spot**: Issuing `put X in/on Y` or `move X to Y` while standing somewhere other than Y returns "Nothing happens" and wastes the turn. Always `go to Y` first. For Pick Two & Place especially, after taking the second instance go back to the destination receptacle BEFORE placing it.
- **Idle look/inventory loop**: If you have placed an object and keep issuing `look`/`inventory` with no change, the task is NOT silently complete — you likely placed the WRONG object type. Re-read the task noun, go find the correct exact-noun object, transform it, and place it; do not waste remaining steps re-confirming an empty hand.
- **Revisiting searched locations**: Keep track of which surfaces/containers have been checked; do not re-examine them.
- **Ignoring visible objects**: If the target object appears in the observation, pick it up immediately.
- **Skipping state changes**: Do not place an object at the destination without first cleaning/heating/cooling it when required.
- **Toggling appliances to transform**: Do not `move X to microwave`, `open`/`close`, or `examine` an appliance to heat/cool/clean. Use the single command `heat/cool/clean X with <appliance> 1` while holding X.
- **Transforming at the destination**: When the delivery receptacle happens to be a microwave/fridge, `put` the object there — do not heat/cool it at the destination. The transform appliance is set by the task verb.
- **Premature termination**: Do not stop the episode until all goal conditions are verified as met.
- **Action loops**: Repeatedly toggling or examining the same object wastes steps. Move on to new locations instead.
