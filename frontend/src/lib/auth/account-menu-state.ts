export interface AccountMenuState {
  open: boolean;
  focus: "none" | "first-item" | "trigger";
}

export type AccountMenuAction =
  | { type: "TOGGLE"; focusFirst?: boolean }
  | { type: "OPEN_WITH_FOCUS" }
  | { type: "CLOSE" }
  | { type: "CLOSE_AND_RESTORE" }
  | { type: "FOCUS_APPLIED" };

export const initialAccountMenuState: AccountMenuState = { open: false, focus: "none" };

export function accountMenuReducer(state: AccountMenuState, action: AccountMenuAction): AccountMenuState {
  switch (action.type) {
    case "TOGGLE":
      return state.open
        ? initialAccountMenuState
        : { open: true, focus: action.focusFirst ? "first-item" : "none" };
    case "OPEN_WITH_FOCUS":
      return { open: true, focus: "first-item" };
    case "CLOSE":
      return initialAccountMenuState;
    case "CLOSE_AND_RESTORE":
      return { open: false, focus: "trigger" };
    case "FOCUS_APPLIED":
      return { ...state, focus: "none" };
    default:
      return state;
  }
}
