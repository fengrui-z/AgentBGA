import unittest

from agentbga.ark_nova_official import (
    ContentEntry,
    SemanticEngine,
    SemanticRuleError,
    apply_association_execution_action,
    legal_association_execution_actions,
    new_semantic_state,
    start_action,
)


def action_card(state: dict, action: str) -> dict:
    return next(card for card in state["players"][0]["action_cards"] if card["action"] == action)


class ArkNovaOfficialAssociationActionTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=37)
        self.state["phase"] = "active"
        self.projects = {}

    def project(self) -> ContentEntry:
        return ContentEntry(
            id="ark-nova:test-zoo-project",
            kind="zoo_conservation_project",
            official_component_id="999",
            source_ids=("scenario",),
            display_title="Test Zoo Project",
            display_summary="Support without a prerequisite.",
            facts={
                "levels": [{
                    "id": "level-1", "requirements": [],
                    "conservation": 1, "reputation": 0,
                }],
            },
            requirements=(), effects=(), references=(),
            review_status="scenario_tested", scenario_tests=("association",),
            reviewer=None, second_reviewer=None,
        )

    def choices(self, state: dict) -> list[dict]:
        return legal_association_execution_actions(
            self.engine, state, 0, self.projects,
        )

    def apply(self, state: dict, action: dict) -> tuple[dict, list[dict]]:
        return apply_association_execution_action(
            self.engine, state, 0, self.projects, action,
        )

    def test_association_one_commits_worker_and_repeated_task_cost_increases(self):
        state = self.state
        state["players"][0]["association_workers"]["active"] = 3
        state["players"][0]["association_workers"]["committed"] = [
            {"task": "gain-reputation"},
        ]
        state, _ = start_action(state, 0, "association")
        reputation = next(
            choice for choice in self.choices(state)
            if choice["action"].get("task_id") == "gain-reputation"
        )
        self.assertEqual(2, reputation["action"]["workers"])
        state, events = self.apply(state, reputation["action"])
        self.assertEqual(1, state["players"][0]["association_workers"]["active"])
        self.assertEqual(3, len(state["players"][0]["association_workers"]["committed"]))
        self.assertEqual(2, state["players"][0]["tracks"]["reputation"])
        self.assertEqual(["association:finish"], [choice["id"] for choice in self.choices(state)])
        self.assertTrue(any(event["type"] == "track_moved" for event in events))

    def test_other_players_prior_task_never_increases_my_worker_cost(self):
        state = self.state
        project = self.project()
        projects = {project.id: project}
        state["conservation_projects"] = [{
            "id": project.id, "instance_id": project.id,
            "base": False, "claims": [], "blocked_levels": [],
        }]
        state["players"][0]["association_workers"]["committed"] = [
            {"task": "conservation-project"},
        ]
        state["players"][1]["association_workers"]["active"] = 1
        state["players"][1]["modifiers"].append({
            "kind": "association_project_strength", "amount": 4,
        })
        state["active_seat"] = 1
        state, _ = start_action(state, 1, "association")
        choices = legal_association_execution_actions(
            self.engine, state, 1, projects,
        )
        support = next(
            choice for choice in choices
            if choice["action"].get("task_id") == "conservation-project"
        )
        self.assertEqual(1, support["action"]["workers"])

    def test_reputation_university_grants_research_icon_and_two_reputation(self):
        state, _ = start_action(self.state, 0, "association")
        university = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("university_id") == "research-reputation"
        )
        state, _ = self.apply(state, university)
        player = state["players"][0]
        self.assertEqual(["research-reputation"], player["universities"])
        self.assertEqual(1, player["icons"]["research"])
        self.assertEqual(2, player["tracks"]["reputation"])
        supply = state["association_board"]["universities"]["research-reputation"]
        self.assertEqual(0, supply["available"])
        self.assertEqual([0], supply["owners"])

    def test_partner_zoo_adds_its_continent_icon(self):
        state, _ = start_action(self.state, 0, "association")
        europe = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("continent") == "europe"
        )
        state, events = self.apply(state, europe)
        self.assertEqual(["europe"], state["players"][0]["partner_zoos"])
        self.assertEqual(1, state["players"][0]["icons"]["europe"])
        self.assertTrue(any(event["type"] == "zoo_icon_entered" for event in events))

    def test_base_game_offers_only_the_three_printed_university_types(self):
        self.assertEqual(
            {"research-2", "research-reputation", "research-hand-limit"},
            set(self.state["association_board"]["universities"]),
        )
        state, _ = start_action(self.state, 0, "association")
        university_ids = {
            choice["action"]["university_id"]
            for choice in self.choices(state)
            if choice["action"].get("task_id") == "university"
        }
        self.assertEqual(
            {"research-2", "research-reputation", "research-hand-limit"},
            university_ids,
        )
        first_university = next(
            choice for choice in self.choices(state)
            if choice["action"].get("university_id") == "research-2"
        )
        self.assertIn("your 1st", first_university["label"])
        self.assertIn("does not upgrade an Action card", first_university["label"])
        self.assertIn("action strength requirement 4", first_university["label"])
        self.assertIn("money cost 0", first_university["label"])

    def test_second_university_label_announces_action_upgrade_without_money_cost(self):
        state = self.state
        state["players"][0]["universities"] = ["research-reputation"]
        state, _ = start_action(state, 0, "association")
        university = next(
            choice for choice in self.choices(state)
            if choice["action"].get("university_id") == "research-2"
        )
        self.assertIn("your 2nd", university["label"])
        self.assertIn("upgrade one Action card", university["label"])
        self.assertIn("money cost 0", university["label"])

    def test_second_asset_requires_action_upgrade_choice(self):
        state = self.state
        state["players"][0]["partner_zoos"] = ["africa"]
        state, _ = start_action(state, 0, "association")
        partner = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("task_id") == "partner-zoo"
            and choice["action"].get("continent") == "asia"
        )
        state, _ = self.apply(state, partner)
        self.assertTrue(all(
            choice["action"]["type"] == "upgrade_association_reward_card"
            for choice in self.choices(state)
        ))
        state, _ = self.apply(state, {
            "type": "upgrade_association_reward_card", "action_card_id": "cards",
        })
        self.assertTrue(action_card(state, "cards")["upgraded"])
        self.assertIn("association:finish", [choice["id"] for choice in self.choices(state)])

    def test_third_partner_zoo_requires_association_two_and_activates_worker(self):
        state = self.state
        player = state["players"][0]
        player["partner_zoos"] = ["africa", "europe"]
        state, _ = start_action(state, 0, "association")
        self.assertFalse(any(
            choice["action"].get("task_id") == "partner-zoo" for choice in self.choices(state)
        ))

        upgraded = new_semantic_state(2)
        upgraded["phase"] = "active"
        upgraded_player = upgraded["players"][0]
        upgraded_player["partner_zoos"] = ["africa", "europe"]
        action_card(upgraded, "association")["upgraded"] = True
        upgraded, _ = start_action(upgraded, 0, "association")
        partner = next(
            choice["action"] for choice in self.choices(upgraded)
            if choice["action"].get("task_id") == "partner-zoo"
            and choice["action"].get("continent") == "asia"
        )
        upgraded, _ = self.apply(upgraded, partner)
        workers = upgraded["players"][0]["association_workers"]
        self.assertEqual(1, workers["active"])
        self.assertEqual(2, workers["reserve"])

    def test_association_two_combines_different_tasks_then_may_donate(self):
        state = self.state
        player = state["players"][0]
        player["association_workers"]["active"] = 3
        player["x_tokens"] = 1
        action_card(state, "association")["upgraded"] = True
        state, _ = start_action(state, 0, "association", x_by_execution=(1,))
        reputation = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("task_id") == "gain-reputation"
        )
        state, _ = self.apply(state, reputation)
        self.assertFalse(any(
            choice["action"].get("task_id") == "gain-reputation" for choice in self.choices(state)
        ))
        partner = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("task_id") == "partner-zoo"
            and choice["action"].get("continent") == "australia"
        )
        state, _ = self.apply(state, partner)
        self.assertIn("association:donate:2", [choice["id"] for choice in self.choices(state)])
        state, _ = self.apply(state, {"type": "make_association_donation", "cost": 2})
        self.assertEqual(23, state["players"][0]["money"])
        self.assertEqual(1, state["players"][0]["tracks"]["conservation"])
        self.assertEqual([{"seat": 0, "cost": 2}], state["donations_made"])
        self.assertNotIn("association:donate:5", [choice["id"] for choice in self.choices(state)])

    def test_stale_asset_choice_is_rejected(self):
        state, _ = start_action(self.state, 0, "association")
        with self.assertRaisesRegex(SemanticRuleError, "not currently legal"):
            self.apply(state, {
                "type": "perform_association_task", "task_id": "partner-zoo",
                "continent": "africa", "strength": 3, "workers": 0,
            })

    def test_twelfth_money_donation_remains_available_after_track_is_full(self):
        state = self.state
        player = state["players"][0]
        player["money"] = 100
        player["association_workers"]["active"] = 2
        action_card(state, "association")["upgraded"] = True
        state["donations_made"] = [
            {"seat": index % 2, "cost": cost}
            for index, cost in enumerate((2, 5, 7, 10, 12, 12))
        ]
        state, _ = start_action(state, 0, "association")
        reputation = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("task_id") == "gain-reputation"
        )
        state, _ = self.apply(state, reputation)
        donation = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"]["type"] == "make_association_donation"
        )
        self.assertEqual(12, donation["cost"])
        state, _ = self.apply(state, donation)
        self.assertEqual(88, state["players"][0]["money"])
        self.assertEqual(7, len(state["donations_made"]))

    def test_task_with_three_committed_workers_cannot_be_used_again(self):
        state = self.state
        state["players"][0]["association_workers"] = {
            "active": 4,
            "reserve": 0,
            "committed": [{"task": "gain-reputation"} for _ in range(3)],
        }
        state, _ = start_action(state, 0, "association")
        self.assertFalse(any(
            choice["action"].get("task_id") == "gain-reputation"
            for choice in self.choices(state)
        ))

    def test_association_one_introduces_project_from_hand_and_supports_it(self):
        state = self.state
        project = self.project()
        self.projects = {project.id: project}
        state["players"][0]["x_tokens"] = 2
        state["players"][0]["hand"] = [{
            "id": "project-hand-a", "entry_id": project.id,
        }]
        state, _ = start_action(state, 0, "association", x_by_execution=(2,))
        choice = next(
            choice for choice in self.choices(state)
            if choice["action"].get("source") == "hand"
            and choice["action"].get("token_slot_id") == "enclosure-2"
            and choice["action"].get("token_bonus_timing") == "after"
        )
        self.assertIn(
            "Build one size-2 standard enclosure for free: once immediately + once at every Break (recurring)",
            choice["label"],
        )
        self.assertEqual(
            "免费建造一个2格普通围栏：立即一次 + 每次休息一次（持续）",
            choice["benefit_summary_cn"],
        )
        self.assertTrue(choice["recurring"])
        action = choice["action"]
        state, events = self.apply(state, action)
        self.assertEqual([], state["players"][0]["hand"])
        self.assertEqual([project.id], state["players"][0]["supported_projects"])
        self.assertEqual(project.id, state["conservation_projects"][0]["id"])
        self.assertEqual(1, state["players"][0]["tracks"]["conservation"])
        self.assertTrue(any(
            event["type"] == "conservation_project_introduced"
            and event["source"] == "hand" and event["folder_cost"] == 0
            for event in events
        ))

    def test_association_two_introduces_reputation_display_project_and_pays_folder(self):
        state = self.state
        project = self.project()
        self.projects = {project.id: project}
        action_card(state, "association")["upgraded"] = True
        state["players"][0]["x_tokens"] = 2
        state["players"][0]["tracks"]["reputation"] = 3
        state["card_display"] = [
            {"id": "other-a"},
            {"id": "project-display-a", "entry_id": project.id},
            *({"id": f"other-{index}"} for index in range(2, 6)),
        ]
        state["zoo_deck"] = [{"id": "replacement"}]
        state, _ = start_action(state, 0, "association", x_by_execution=(2,))
        action = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("source") == "display"
            and choice["action"].get("token_slot_id") == "x-3"
            and choice["action"].get("token_bonus_timing") == "after"
        )
        self.assertEqual(2, action["folder_cost"])
        state, events = self.apply(state, action)
        self.assertEqual(23, state["players"][0]["money"])
        self.assertNotIn("project-display-a", [card["id"] for card in state["card_display"]])
        introduced = next(
            event for event in events if event["type"] == "conservation_project_introduced"
        )
        self.assertEqual(2, introduced["folder_cost"])
        state, events = self.apply(state, {"type": "finish_association_action"})
        self.assertEqual(6, len(state["card_display"]))
        self.assertTrue(any(event["type"] == "card_display_refilled" for event in events))

    def test_association_one_cannot_introduce_project_from_display(self):
        state = self.state
        project = self.project()
        self.projects = {project.id: project}
        state["players"][0]["x_tokens"] = 2
        next(
            card for card in state["players"][0]["action_cards"]
            if card["action"] == "cards"
        )["upgraded"] = True
        state["players"][0]["tracks"]["reputation"] = 15
        state["card_display"] = [{
            "id": "project-display-a", "entry_id": project.id,
        }]
        state, _ = start_action(state, 0, "association", x_by_execution=(2,))
        self.assertFalse(any(
            choice["action"].get("source") == "display" for choice in self.choices(state)
        ))

    def test_unused_base_project_taken_into_hand_can_be_introduced_above_board(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        from agentbga.ark_nova_official import load_content_pack
        pack = load_content_pack(root / "content-packs" / "ark-nova" / "base-en-draft")
        project = pack.entry("ark-nova:base-project-103")
        self.projects = {project.id: project}
        state = self.state
        state["players"][0]["icons"]["africa"] = 2
        state["players"][0]["x_tokens"] = 2
        state["players"][0]["hand"] = [{
            "id": "asserted-africa", "entry_id": project.id,
        }]
        state, _ = start_action(state, 0, "association", x_by_execution=(2,))
        action = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("instance_id") == "asserted-africa"
            and choice["action"].get("token_slot_id") == "x-3"
            and choice["action"].get("token_bonus_timing") == "after"
        )
        state, _ = self.apply(state, action)
        project_state = next(
            item for item in state["conservation_projects"] if item["id"] == project.id
        )
        self.assertFalse(project_state["base"])
        self.assertEqual("asserted-africa", project_state["instance_id"])


if __name__ == "__main__":
    unittest.main()
