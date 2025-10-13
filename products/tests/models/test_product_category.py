from django.test import TestCase
from django.core.exceptions import ValidationError

from products import models
from products import factories

class TestProductCategoryDepthValidation(TestCase):
    Factory = factories.ProductCategoryFactory

    def setUp(self):
        self.root_category = self.Factory(is_root=True)
        self.child_category = self.Factory(parent=self.root_category)
        self.grandchild_category = self.Factory(parent=self.child_category)

    def test_cannot_create_category_deeper_than_level_2(self):
        too_deep = self.Factory.build(parent=self.grandchild_category)
        with self.assertRaises(ValidationError):
            too_deep.full_clean()

    def test_cannot_move_category_to_invalid_depth(self):
        root = self.Factory(is_root=True, children=3)
        root.parent = self.child_category
        with self.assertRaises(ValidationError):
            root.full_clean()


class TestProductCategoryActivationLogic(TestCase):
    Factory = factories.ProductCategoryFactory

    def setUp(self):
        self.nodes = []
        for i in range(3):
            self.nodes.append(
                self.Factory(
                    is_root=(i == 0),
                    is_active=False,
                    parent=self.nodes[i - 1] if i > 0 else None
                )
            )
        self.root, self.child, self.grandchild = self.nodes

    def _refresh_all(self, *objects):
        for node in self.nodes + list(objects):
            node.refresh_from_db()

    def test_activating_child_activates_all_ancestors(self):
        self.grandchild.is_active = True
        self.grandchild.save()
        self._refresh_all()
        self.assertTrue(all([node.is_active for node in self.nodes]))

    def test_deactivating_child_deactivates_all_up_to_root(self):
        models.ProductCategory.objects.update(is_active=True)
        self.grandchild.is_active = False
        self.grandchild.save()
        self._refresh_all()
        self.assertTrue([not node.is_active for node in self.nodes])

    def test_deactivating_branch_does_not_affect_other_active_branches(self):
        models.ProductCategory.objects.update(is_active=True)
        self._refresh_all()
        child_2 = self.Factory(parent=self.root)
        grandchild_2 = self.Factory(parent=child_2)
        self.grandchild.is_active = False
        self.grandchild.save()
        self._refresh_all(child_2, grandchild_2)
        self.assertTrue(grandchild_2.is_active)
        self.assertTrue(child_2.is_active)
        self.assertTrue(self.root.is_active)
        self.assertFalse(self.child.is_active)
        self.assertFalse(self.grandchild.is_active)

    def test_activating_node_reactivates_entire_family(self):
        # all inactive by default
        self.child.is_active = True
        self.child.save()
        self._refresh_all()
        self.assertTrue(self.root.is_active)
        self.assertTrue(self.child.is_active)
        self.assertTrue(self.grandchild.is_active)

    def test_moving_node_propagates_activation_correctly(self):
        self.grandchild.is_active = True
        self.grandchild.save()
        self._refresh_all()
        root_2 = self.Factory(is_root=True, is_active=False)
        self.grandchild.parent = root_2
        self.grandchild.save()
        self._refresh_all(root_2)
        self.assertFalse(self.root.is_active)
        self.assertTrue(root_2.is_active)
        self.assertTrue(self.grandchild.is_active)

    def test_deleting_active_grandchild_deactivates_inactive_ancestors(self):
        models.ProductCategory.objects.update(is_active=True)
        self._refresh_all()
        self.grandchild.delete()
        self.root.refresh_from_db()
        self.child.refresh_from_db()
        self.assertFalse(self.child.is_active)
        self.assertFalse(self.root.is_active)

    def test_deleting_branch_does_not_affect_other_branches(self):
        models.ProductCategory.objects.update(is_active=True)
        self._refresh_all()
        child_2 = self.Factory(parent=self.root, is_active=True)
        grandchild_2 = self.Factory(parent=child_2, is_active=True)
        grandchild_2.delete()
        self._refresh_all(child_2)
        self.assertTrue(self.root.is_active)
        self.assertTrue(self.child.is_active)
        self.assertTrue(self.grandchild.is_active)
        self.assertFalse(child_2.is_active)

