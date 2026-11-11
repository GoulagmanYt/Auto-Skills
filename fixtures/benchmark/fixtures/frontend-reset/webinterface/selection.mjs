export function reduceSelection(state, action) {
  if (action.type === "reset") {
    return { ...state, selectedIds: [] };
  }
  if (action.type === "select") {
    return { ...state, selectedIds: [...new Set([...state.selectedIds, action.id])], anchorId: action.id };
  }
  return state;
}
