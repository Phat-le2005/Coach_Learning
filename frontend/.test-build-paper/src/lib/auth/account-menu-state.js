"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.initialAccountMenuState = void 0;
exports.accountMenuReducer = accountMenuReducer;
exports.initialAccountMenuState = { open: false, focus: "none" };
function accountMenuReducer(state, action) {
    switch (action.type) {
        case "TOGGLE":
            return state.open
                ? exports.initialAccountMenuState
                : { open: true, focus: action.focusFirst ? "first-item" : "none" };
        case "OPEN_WITH_FOCUS":
            return { open: true, focus: "first-item" };
        case "CLOSE":
            return exports.initialAccountMenuState;
        case "CLOSE_AND_RESTORE":
            return { open: false, focus: "trigger" };
        case "FOCUS_APPLIED":
            return Object.assign(Object.assign({}, state), { focus: "none" });
        default:
            return state;
    }
}
