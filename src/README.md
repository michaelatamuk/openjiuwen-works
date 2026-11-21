# src

The product will be built here: the window and the engine.

Nothing is implemented yet. When work starts, this is the expected shape:

```
src/
  window/      the surface where people report, watch and approve
  engine/      queue, planning, dispatch, verification, evidence, metrics
  policy/      what a flow may touch, and where a person must step in
```

The engine is the only component that decides what happens next. It calls the other products —
it does not modify them.
