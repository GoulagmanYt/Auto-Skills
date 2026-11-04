import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const { reduceSelection } = await import(pathToFileURL(resolve(process.argv[2], "webinterface/selection.mjs")));
for (const ids of [["a"], ["a", "b"], []]) {
  const items = Object.freeze(["a", "b", "c"]);
  const state = Object.freeze({ selectedIds: Object.freeze(ids), anchorId: "a", pendingRequest: "request-1", items, label: "preserved" });
  const reset = reduceSelection(state, { type: "reset" });
  assert.deepEqual(reset.selectedIds, []);
  assert.equal(reset.anchorId, null);
  assert.equal(reset.pendingRequest, null);
  assert.equal(reset.items, items);
  assert.equal(reset.label, "preserved");
  assert.notEqual(reset, state);
  assert.equal(state.anchorId, "a");
  assert.equal(state.pendingRequest, "request-1");
  const selected = reduceSelection(reset, { type: "select", id: "b" });
  assert.deepEqual(selected.selectedIds, ["b"]);
  assert.equal(selected.anchorId, "b");
  assert.deepEqual(reduceSelection(selected, { type: "select", id: "b" }).selectedIds, ["b"]);
  assert.equal(reduceSelection(state, { type: "unknown" }), state);
}
console.log("Selection reset checks passed");
