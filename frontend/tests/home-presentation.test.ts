import assert from "node:assert/strict";
import test from "node:test";
import { getHomeRoutes, homeTaskHref, homeTaskTypeLabel, homeDate } from "../src/features/student-home/home-presentation";
import type { StudentHomeViewModel, StudyTaskItemViewModel } from "../src/features/student-home/types";

function home(type = "CONTINUE_PRACTICE", available = true) {
  return { subject: { id: "subject & 12", name: "Toán" }, resolvedAction: {
    type, hasAvailableRoute: available, route: "/student/attempts/existing-attempt",
  } } as StudentHomeViewModel;
}
test("homepage retains the authoritative continuation instead of launching another session", () => {
  const routes = getHomeRoutes(home());
  assert.equal(routes.resume, "/student/attempts/existing-attempt");
  assert.equal(routes.practice, "/student/practice?subject_id=subject%20%26%2012");
  assert.equal(routes.knowledge, "/student/knowledge?subject_id=subject%20%26%2012");
});
test("unavailable or idle actions cannot masquerade as an active continuation", () => {
  assert.equal(getHomeRoutes(home("CONTINUE_REPAIR", false)).resume, null);
  assert.equal(getHomeRoutes(home("IDLE")).resume, null);
  assert.equal(getHomeRoutes(home("REVIEW_DUE")).resume, null);
});
test("today's task retains subject and the authoritative problem type, including URL escaping", () => {
  const task = { problemTypeId: "type & one", conceptId: "unused" } as StudyTaskItemViewModel;
  const url = new URL(homeTaskHref(task, "subject one"), "http://local.test");
  assert.equal(url.searchParams.get("subject_id"), "subject one");
  assert.equal(url.searchParams.get("problem_type_id"), "type & one");
  assert.equal(url.searchParams.has("concept_id"), false);
});
test("concept tasks keep their target; untargeted tasks never invent a reference", () => {
  const concept = new URL(homeTaskHref({ conceptId: "concept-id" } as StudyTaskItemViewModel, "subject"), "http://local.test");
  assert.equal(concept.searchParams.get("concept_id"), "concept-id");
  const general = new URL(homeTaskHref({} as StudyTaskItemViewModel, "subject"), "http://local.test");
  assert.equal(general.searchParams.size, 1);
  assert.equal(homeTaskHref({} as StudyTaskItemViewModel, ""), "/student/practice");
});

test("review, today's task and learning priority retain their authoritative next-action target", () => {
  for (const type of ["REVIEW_DUE", "TODAY_TASK", "LEARNING_PRIORITY"]) {
    const state = home(type);
    state.resolvedAction.route = "/student/practice?concept_id=real-target";
    assert.equal(getHomeRoutes(state).recommended, state.resolvedAction.route);
    assert.equal(getHomeRoutes(state).resume, null);
  }
});
test("unavailable and idle recommendations cannot acquire a launch route", () => {
  assert.equal(getHomeRoutes(home("REVIEW_DUE", false)).recommended, null);
  assert.equal(getHomeRoutes(home("IDLE")).recommended, null);
});
test("task metadata stays recognizable and invalid dates do not become fabricated deadlines", () => {
  assert.equal(homeTaskTypeLabel("SPACED_REVIEW"), "Ôn tập");
  assert.equal(homeTaskTypeLabel("EXAM"), "Luyện đề");
  assert.equal(homeTaskTypeLabel("CONCEPT_ACQUISITION"), "Học kiến thức");
  assert.equal(homeDate("2026-11-07T20:00:00Z"), "08/11");
  assert.equal(homeDate("not-a-date"), null);
  assert.equal(homeDate(undefined), null);
});
