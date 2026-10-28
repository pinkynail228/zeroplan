# TUI tests to retire in 0.5.2 (audit 2026-10-23)

Read-only audit of tests/test_tui*.py against docs/RELEASE_0.5.2_PLAN.md, durations from devtools/fasttest.py.
57 candidates, ~131 s; 31 plain deletes. Each integration run deletes (not rewrites) the tests of the UI it replaces;
"shrink" = keep the data/safety assertion, drop the old-UI assertion. Lines are as of main 2026-10-23 and drift.

| Run | Delete | Shrink |
|---|---|---|
| i1b | test_tui_flow FlowTabTests a4_an_active_attempt_draws_the_flow_on_the_live_tab, a4_a_resize_re_measures_the_drawn_boxes | test_tui_milestones PaneTabTests a1_the_live_tab_shows_the_live_lines (keep fallback + tail order) |
| i1c | test_tui_milestones JournalTabTests (all 5) | ArrowTabTests a1_left_right_cycle_the_tabs (2-tab cycle; also covers PaneTabTests a1_the_arrows_switch_the_tab_from_anywhere -> delete that), a5_a_click_on_a_tab_label_switches_to_it |
| i2 | test_tui_live KeyBarTests u5_bar_shrinks_in_the_documented_order; test_tui_polish BarOracleTests (3, keep only if modal bars use them); test_tui_milestones PaneTabTests a4_regression_the_tab_hint_names_the_arrows, a2_regression_the_tab_keys_stay_named_with_a_running_attempt | KeyBarTests la5_no_bar_cuts_a_word (one "primary actions reachable" check), la5_the_bar_text_is_whole (modal bars only); PilotBarTests a1 (modal only); test_tui LayoutTests input_focus_and_tab_toggle (focus only); ArrowTabTests a4_the_old_keys_are_unbound (keep "unbound"); PaneTabTests a3_* (focus, drop letters) |
| i3a | test_tui_chat GoalDraftTests u3_no_goal_draft_reserves_no_key, u3_an_actionable_goal_draft_reserves_the_key, u3_the_reserved_label_survives_the_crowded_panel_bar_at_80x24, u3_each_draft_line_names_the_reply_it_comes_from, the_draft_key_is_text_in_every_editor_and_inert_under_any_modal | u3_the_newest_actionable_goal_draft_is_the_choice, u3_a_draft_pushed_out_of_the_retained_history_loses_the_key, d2_* (4; trigger becomes the card) |
| i3d | test_tui_chat AnswerDraftTests d3b_the_answer_key_is_text_in_every_editor, d3b_both_reserved_labels_and_the_exit_hint_fit, a2_regression_the_tab_keys_stay_named_beside_both_reserved_drafts | d3b_a_draft_for_another_milestone_offers_no_key |
| i8 | test_tui_polish EndViewTests (5), ResultModalTests a3_below_the_header_journal_details_and_return; test_tui_flow DrawTests (11, with flow.py) | — |

Keep (data/safety, even though they press letters; rewrite the trigger only): test_tui_live PanelTests la2 (journal persistence),
PlanScreenTests and test_tui_plan_gate (plan-gate logic, i3b), test_tui_milestones end-token safety and JourneyTests (i2),
test_tui a1_start_focus_is_the_chat_input_and_typed_keys_are_text (D4).
