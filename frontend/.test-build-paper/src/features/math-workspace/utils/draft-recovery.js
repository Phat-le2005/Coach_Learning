"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.restoreDirtyPageDrafts = restoreDirtyPageDrafts;
exports.canSafelyRebaseInkDraft = canSafelyRebaseInkDraft;
/** Restore only unsynchronized drafts; never replace ink edited since this page mounted. */
function restoreDirtyPageDrafts(pages, drafts, locallyEditedPages, maxPages) {
    var _a;
    const next = new Map(pages);
    const restored = [];
    for (const draft of drafts) {
        if (!draft.isDirty || !Number.isInteger(draft.pageIndex) || draft.pageIndex < 0 || draft.pageIndex >= maxPages)
            continue;
        if (locallyEditedPages.has(draft.pageIndex) || ((_a = next.get(draft.pageIndex)) === null || _a === void 0 ? void 0 : _a.isDirty))
            continue;
        next.set(draft.pageIndex, {
            strokes: draft.strokes,
            past: [],
            future: [],
            isDirty: true,
        });
        restored.push(draft);
    }
    return { pages: next, restored };
}
/** A document revision covers every page. A stale revision alone does not mean
 * this page changed. Rebase only when the server strokes are an exact prefix of
 * the local strokes (the normal append-only drawing case). Erasures or edits
 * against a changed page need an explicit user decision. */
function canSafelyRebaseInkDraft(localStrokes, serverStrokes) {
    if (serverStrokes.length > localStrokes.length)
        return false;
    return serverStrokes.every((serverStroke, index) => {
        const localStroke = localStrokes[index];
        if (!localStroke || serverStroke.id !== localStroke.id)
            return false;
        if (serverStroke.tool !== localStroke.tool || serverStroke.color !== localStroke.color || serverStroke.width !== localStroke.width)
            return false;
        if (serverStroke.points.length !== localStroke.points.length)
            return false;
        return serverStroke.points.every((point, pointIndex) => {
            var _a, _b;
            const localPoint = localStroke.points[pointIndex];
            return localPoint && point.x === localPoint.x && point.y === localPoint.y
                && ((_a = point.pressure) !== null && _a !== void 0 ? _a : 0.5) === ((_b = localPoint.pressure) !== null && _b !== void 0 ? _b : 0.5);
        });
    });
}
