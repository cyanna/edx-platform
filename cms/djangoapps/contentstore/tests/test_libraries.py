"""
Content library unit tests that require the CMS runtime.
"""
from contentstore.tests.utils import AjaxEnabledTestClient, parse_json
from contentstore.utils import reverse_url, reverse_usage_url, reverse_library_url
from contentstore.views.preview import _load_preview_module
from contentstore.views.tests.test_library import LIBRARY_REST_URL
import ddt
from mock import patch
from student.auth import has_studio_read_access, has_studio_write_access
from student.roles import (
    CourseInstructorRole, CourseStaffRole, CourseCreatorRole, LibraryUserRole,
    OrgStaffRole, OrgInstructorRole, OrgLibraryUserRole,
)
from xblock.reference.user_service import XBlockUser
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from mock import Mock
from opaque_keys.edx.locator import CourseKey, LibraryLocator
from openedx.core.djangoapps.content.course_structures.tests import SignalDisconnectTestMixin


class LibraryTestCase(ModuleStoreTestCase):
    """
    Common functionality for content libraries tests
    """
    def setUp(self):
        user_password = super(LibraryTestCase, self).setUp()

        self.client = AjaxEnabledTestClient()
        self.client.login(username=self.user.username, password=user_password)

        self.lib_key = self._create_library()
        self.library = modulestore().get_library(self.lib_key)

        self.session_data = {}  # Used by _bind_module

    def _create_library(self, org="org", library="lib", display_name="Test Library"):
        """
        Helper method used to create a library. Uses the REST API.
        """
        response = self.client.ajax_post(LIBRARY_REST_URL, {
            'org': org,
            'library': library,
            'display_name': display_name,
        })
        self.assertEqual(response.status_code, 200)
        lib_info = parse_json(response)
        lib_key = CourseKey.from_string(lib_info['library_key'])
        self.assertIsInstance(lib_key, LibraryLocator)
        return lib_key

    def _add_library_content_block(self, course, library_key, other_settings=None):
        """
        Helper method to add a LibraryContent block to a course.
        The block will be configured to select content from the library
        specified by library_key.
        other_settings can be a dict of Scope.settings fields to set on the block.
        """
        return ItemFactory.create(
            category='library_content',
            parent_location=course.location,
            user_id=self.user.id,
            publish_item=False,
            source_library_id=unicode(library_key),
            **(other_settings or {})
        )

    def _add_simple_content_block(self):
        """ Adds simple HTML block to library """
        return ItemFactory.create(
            category="html", parent_location=self.library.location,
            user_id=self.user.id, publish_item=False
        )

    def _refresh_children(self, lib_content_block, status_code_expected=200):
        """
        Helper method: Uses the REST API to call the 'refresh_children' handler
        of a LibraryContent block
        """
        if 'user' not in lib_content_block.runtime._services:  # pylint: disable=protected-access
            mocked_user_service = Mock(user_id=self.user.id)
            mocked_user_service.get_current_user.return_value = XBlockUser(is_current_user=True)
            lib_content_block.runtime._services['user'] = mocked_user_service  # pylint: disable=protected-access

        handler_url = reverse_usage_url(
            'component_handler',
            lib_content_block.location,
            kwargs={'handler': 'refresh_children'}
        )
        response = self.client.ajax_post(handler_url)
        self.assertEqual(response.status_code, status_code_expected)
        return modulestore().get_item(lib_content_block.location)

    def _bind_module(self, descriptor, user=None):
        """
        Helper to use the CMS's module system so we can access student-specific fields.
        """
        if user is None:
            user = self.user
        if user not in self.session_data:
            self.session_data[user] = {}
        request = Mock(user=user, session=self.session_data[user])
        _load_preview_module(request, descriptor)  # pylint: disable=protected-access

    def _update_item(self, usage_key, metadata):
        """
        Helper method: Uses the REST API to update the fields of an XBlock.
        This will result in the XBlock's editor_saved() method being called.
        """
        update_url = reverse_usage_url("xblock_handler", usage_key)
        return self.client.ajax_post(
            update_url,
            data={
                'metadata': metadata,
            }
        )

    def _list_libraries(self):
        """
        Use the REST API to get a list of libraries visible to the current user.
        """
        response = self.client.get_json(LIBRARY_REST_URL)
        self.assertEqual(response.status_code, 200)
        return parse_json(response)


@ddt.ddt
class TestLibraries(LibraryTestCase):
    """
    High-level tests for libraries
    """
    @ddt.data(
        (2, 1, 1),
        (2, 2, 2),
        (2, 20, 2),
    )
    @ddt.unpack
    def test_max_items(self, num_to_create, num_to_select, num_expected):
        """
        Test the 'max_count' property of LibraryContent blocks.
        """
        for _ in range(0, num_to_create):
            self._add_simple_content_block()

        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        lc_block = self._add_library_content_block(course, self.lib_key, {'max_count': num_to_select})
        self.assertEqual(len(lc_block.children), 0)
        lc_block = self._refresh_children(lc_block)

        # Now, we want to make sure that .children has the total # of potential
        # children, and that get_child_descriptors() returns the actual children
        # chosen for a given student.
        # In order to be able to call get_child_descriptors(), we must first
        # call bind_for_student:
        self._bind_module(lc_block)
        self.assertEqual(len(lc_block.children), num_to_create)
        self.assertEqual(len(lc_block.get_child_descriptors()), num_expected)

    def test_consistent_children(self):
        """
        Test that the same student will always see the same selected child block
        """
        # Create many blocks in the library and add them to a course:
        for num in range(0, 8):
            ItemFactory.create(
                data="This is #{}".format(num + 1),
                category="html", parent_location=self.library.location, user_id=self.user.id, publish_item=False
            )

        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        lc_block = self._add_library_content_block(course, self.lib_key, {'max_count': 1})
        lc_block_key = lc_block.location
        lc_block = self._refresh_children(lc_block)

        def get_child_of_lc_block(block):
            """
            Fetch the child shown to the current user.
            """
            children = block.get_child_descriptors()
            self.assertEqual(len(children), 1)
            return children[0]

        # Check which child a student will see:
        self._bind_module(lc_block)
        chosen_child = get_child_of_lc_block(lc_block)
        chosen_child_defn_id = chosen_child.definition_locator.definition_id
        lc_block.save()

        modulestore().update_item(lc_block, self.user.id)

        # Now re-load the block and try again:
        def check():
            """
            Confirm that chosen_child is still the child seen by the test student
            """
            for _ in range(0, 6):  # Repeat many times b/c blocks are randomized
                lc_block = modulestore().get_item(lc_block_key)  # Reload block from the database
                self._bind_module(lc_block)
                current_child = get_child_of_lc_block(lc_block)
                self.assertEqual(current_child.location, chosen_child.location)
                self.assertEqual(current_child.data, chosen_child.data)
                self.assertEqual(current_child.definition_locator.definition_id, chosen_child_defn_id)

        check()
        # Refresh the children:
        lc_block = self._refresh_children(lc_block)
        # Now re-load the block and try yet again, in case refreshing the children changed anything:
        check()

    def test_definition_shared_with_library(self):
        """
        Test that the same block definition is used for the library and course[s]
        """
        block1 = self._add_simple_content_block()
        def_id1 = block1.definition_locator.definition_id
        block2 = self._add_simple_content_block()
        def_id2 = block2.definition_locator.definition_id
        self.assertNotEqual(def_id1, def_id2)

        # Next, create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        lc_block = self._add_library_content_block(course, self.lib_key)
        lc_block = self._refresh_children(lc_block)
        for child_key in lc_block.children:
            child = modulestore().get_item(child_key)
            def_id = child.definition_locator.definition_id
            self.assertIn(def_id, (def_id1, def_id2))

    def test_fields(self):
        """
        Test that blocks used from a library have the same field values as
        defined by the library author.
        """
        data_value = "A Scope.content value"
        name_value = "A Scope.settings value"
        lib_block = ItemFactory.create(
            category="html",
            parent_location=self.library.location,
            user_id=self.user.id,
            publish_item=False,
            display_name=name_value,
            data=data_value,
        )
        self.assertEqual(lib_block.data, data_value)
        self.assertEqual(lib_block.display_name, name_value)

        # Next, create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        lc_block = self._add_library_content_block(course, self.lib_key)
        lc_block = self._refresh_children(lc_block)
        course_block = modulestore().get_item(lc_block.children[0])

        self.assertEqual(course_block.data, data_value)
        self.assertEqual(course_block.display_name, name_value)

    def test_block_with_children(self):
        """
        Test that blocks used from a library can have children.
        """
        data_value = "A Scope.content value"
        name_value = "A Scope.settings value"
        # In the library, create a vertical block with a child:
        vert_block = ItemFactory.create(
            category="vertical",
            parent_location=self.library.location,
            user_id=self.user.id,
            publish_item=False,
        )
        child_block = ItemFactory.create(
            category="html",
            parent_location=vert_block.location,
            user_id=self.user.id,
            publish_item=False,
            display_name=name_value,
            data=data_value,
        )
        self.assertEqual(child_block.data, data_value)
        self.assertEqual(child_block.display_name, name_value)

        # Next, create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        lc_block = self._add_library_content_block(course, self.lib_key)
        lc_block = self._refresh_children(lc_block)
        self.assertEqual(len(lc_block.children), 1)
        course_vert_block = modulestore().get_item(lc_block.children[0])
        self.assertEqual(len(course_vert_block.children), 1)
        course_child_block = modulestore().get_item(course_vert_block.children[0])

        self.assertEqual(course_child_block.data, data_value)
        self.assertEqual(course_child_block.display_name, name_value)

    def test_change_after_first_sync(self):
        """
        Check that nothing goes wrong if we (A) Set up a LibraryContent block
        and use it successfully, then (B) Give it an invalid configuration.
        No children should be deleted until the configuration is fixed.
        """
        # Add a block to the library:
        data_value = "Hello world!"
        ItemFactory.create(
            category="html",
            parent_location=self.library.location,
            user_id=self.user.id,
            publish_item=False,
            display_name="HTML BLock",
            data=data_value,
        )
        # Create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        lc_block = self._add_library_content_block(course, self.lib_key)
        lc_block = self._refresh_children(lc_block)
        self.assertEqual(len(lc_block.children), 1)

        # Now, change the block settings to have an invalid library key:
        resp = self._update_item(
            lc_block.location,
            {"source_library_id": "library-v1:NOT+FOUND"},
        )
        self.assertEqual(resp.status_code, 200)
        lc_block = modulestore().get_item(lc_block.location)
        self.assertEqual(len(lc_block.children), 1)  # Children should not be deleted due to a bad setting.
        html_block = modulestore().get_item(lc_block.children[0])
        self.assertEqual(html_block.data, data_value)

    def test_refreshes_children_if_libraries_change(self):
        """ Tests that children are automatically refreshed if libraries list changes """
        library2key = self._create_library("org2", "lib2", "Library2")
        library2 = modulestore().get_library(library2key)
        data1, data2 = "Hello world!", "Hello other world!"
        ItemFactory.create(
            category="html",
            parent_location=self.library.location,
            user_id=self.user.id,
            publish_item=False,
            display_name="Lib1: HTML BLock",
            data=data1,
        )

        ItemFactory.create(
            category="html",
            parent_location=library2.location,
            user_id=self.user.id,
            publish_item=False,
            display_name="Lib 2: HTML BLock",
            data=data2,
        )

        # Create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        lc_block = self._add_library_content_block(course, self.lib_key)
        lc_block = self._refresh_children(lc_block)
        self.assertEqual(len(lc_block.children), 1)

        # Now, change the block settings to have an invalid library key:
        resp = self._update_item(
            lc_block.location,
            {"source_library_id": str(library2key)},
        )
        self.assertEqual(resp.status_code, 200)
        lc_block = modulestore().get_item(lc_block.location)

        self.assertEqual(len(lc_block.children), 1)
        html_block = modulestore().get_item(lc_block.children[0])
        self.assertEqual(html_block.data, data2)

    @patch("xmodule.library_tools.SearchEngine.get_search_engine", Mock(return_value=None))
    def test_refreshes_children_if_capa_type_change(self):
        """ Tests that children are automatically refreshed if capa type field changes """
        name1, name2 = "Option Problem", "Multiple Choice Problem"
        ItemFactory.create(
            category="problem",
            parent_location=self.library.location,
            user_id=self.user.id,
            publish_item=False,
            display_name=name1,
            data="<problem><optionresponse></optionresponse></problem>",
        )
        ItemFactory.create(
            category="problem",
            parent_location=self.library.location,
            user_id=self.user.id,
            publish_item=False,
            display_name=name2,
            data="<problem><multiplechoiceresponse></multiplechoiceresponse></problem>",
        )

        # Create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        lc_block = self._add_library_content_block(course, self.lib_key)
        lc_block = self._refresh_children(lc_block)
        self.assertEqual(len(lc_block.children), 2)

        resp = self._update_item(
            lc_block.location,
            {"capa_type": 'optionresponse'},
        )
        self.assertEqual(resp.status_code, 200)
        lc_block = modulestore().get_item(lc_block.location)

        self.assertEqual(len(lc_block.children), 1)
        html_block = modulestore().get_item(lc_block.children[0])
        self.assertEqual(html_block.display_name, name1)

        resp = self._update_item(
            lc_block.location,
            {"capa_type": 'multiplechoiceresponse'},
        )
        self.assertEqual(resp.status_code, 200)
        lc_block = modulestore().get_item(lc_block.location)

        self.assertEqual(len(lc_block.children), 1)
        html_block = modulestore().get_item(lc_block.children[0])
        self.assertEqual(html_block.display_name, name2)

    def test_refresh_fails_for_unknown_library(self):
        """ Tests that refresh children fails if unknown library is configured """
        # Create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        lc_block = self._add_library_content_block(course, self.lib_key)
        lc_block = self._refresh_children(lc_block)
        self.assertEqual(len(lc_block.children), 0)

        # Now, change the block settings to have an invalid library key:
        resp = self._update_item(
            lc_block.location,
            {"source_library_id": "library-v1:NOT+FOUND"},
        )
        self.assertEqual(resp.status_code, 200)
        with self.assertRaises(ValueError):
            self._refresh_children(lc_block, status_code_expected=400)


@ddt.ddt
class TestLibraryAccess(SignalDisconnectTestMixin, LibraryTestCase):
    """
    Test Roles and Permissions related to Content Libraries
    """
    def setUp(self):
        """ Create a library, staff user, and non-staff user """
        super(TestLibraryAccess, self).setUp()
        self.non_staff_user, self.non_staff_user_password = self.create_non_staff_user()

    def _login_as_non_staff_user(self, logout_first=True):
        """ Login as a user that starts out with no roles/permissions granted. """
        if logout_first:
            self.client.logout()  # We start logged in as a staff user
        self.client.login(username=self.non_staff_user.username, password=self.non_staff_user_password)

    def _assert_cannot_create_library(self, org="org", library="libfail", expected_code=403):
        """ Ensure the current user is not able to create a library. """
        self.assertTrue(expected_code >= 300)
        response = self.client.ajax_post(
            LIBRARY_REST_URL,
            {'org': org, 'library': library, 'display_name': "Irrelevant"}
        )
        self.assertEqual(response.status_code, expected_code)
        key = LibraryLocator(org=org, library=library)
        self.assertEqual(modulestore().get_library(key), None)

    def _can_access_library(self, library):
        """
        Use the normal studio library URL to check if we have access

        `library` can be a LibraryLocator or the library's root XBlock
        """
        if isinstance(library, (basestring, LibraryLocator)):
            lib_key = library
        else:
            lib_key = library.location.library_key
        response = self.client.get(reverse_library_url('library_handler', unicode(lib_key)))
        self.assertIn(response.status_code, (200, 302, 403))
        return response.status_code == 200

    def tearDown(self):
        """
        Log out when done each test
        """
        self.client.logout()
        super(TestLibraryAccess, self).tearDown()

    def test_creation(self):
        """
        The user that creates a library should have instructor (admin) and staff permissions
        """
        # self.library has been auto-created by the staff user.
        self.assertTrue(has_studio_write_access(self.user, self.lib_key))
        self.assertTrue(has_studio_read_access(self.user, self.lib_key))
        # Make sure the user was actually assigned the instructor role and not just using is_staff superpowers:
        self.assertTrue(CourseInstructorRole(self.lib_key).has_user(self.user))

        # Now log out and ensure we are forbidden from creating a library:
        self.client.logout()
        self._assert_cannot_create_library(expected_code=302)  # 302 redirect to login expected

        # Now create a non-staff user with no permissions:
        self._login_as_non_staff_user(logout_first=False)
        self.assertFalse(CourseCreatorRole().has_user(self.non_staff_user))

        # Now check that logged-in users without any permissions cannot create libraries
        with patch.dict('django.conf.settings.FEATURES', {'ENABLE_CREATOR_GROUP': True}):
            self._assert_cannot_create_library()

    @ddt.data(
        CourseInstructorRole,
        CourseStaffRole,
        LibraryUserRole,
    )
    def test_acccess(self, access_role):
        """
        Test the various roles that allow viewing libraries are working correctly.
        """
        # At this point, one library exists, created by the currently-logged-in staff user.
        # Create another library as staff:
        library2_key = self._create_library(library="lib2")
        # Login as non_staff_user:
        self._login_as_non_staff_user()

        # non_staff_user shouldn't be able to access any libraries:
        lib_list = self._list_libraries()
        self.assertEqual(len(lib_list), 0)
        self.assertFalse(self._can_access_library(self.library))
        self.assertFalse(self._can_access_library(library2_key))

        # Now manually intervene to give non_staff_user access to library2_key:
        access_role(library2_key).add_users(self.non_staff_user)

        # Now non_staff_user should be able to access library2_key only:
        lib_list = self._list_libraries()
        self.assertEqual(len(lib_list), 1)
        self.assertEqual(lib_list[0]["library_key"], unicode(library2_key))
        self.assertTrue(self._can_access_library(library2_key))
        self.assertFalse(self._can_access_library(self.library))

    @ddt.data(
        OrgStaffRole,
        OrgInstructorRole,
        OrgLibraryUserRole,
    )
    def test_org_based_access(self, org_access_role):
        """
        Test the various roles that allow viewing all of an organization's
        libraries are working correctly.
        """
        # Create some libraries as the staff user:
        lib_key_pacific = self._create_library(org="PacificX", library="libP")
        lib_key_atlantic = self._create_library(org="AtlanticX", library="libA")

        # Login as a non-staff:
        self._login_as_non_staff_user()

        # Now manually intervene to give non_staff_user access to all "PacificX" libraries:
        org_access_role(lib_key_pacific.org).add_users(self.non_staff_user)

        # Now non_staff_user should be able to access lib_key_pacific only:
        lib_list = self._list_libraries()
        self.assertEqual(len(lib_list), 1)
        self.assertEqual(lib_list[0]["library_key"], unicode(lib_key_pacific))
        self.assertTrue(self._can_access_library(lib_key_pacific))
        self.assertFalse(self._can_access_library(lib_key_atlantic))
        self.assertFalse(self._can_access_library(self.lib_key))

    @ddt.data(True, False)
    def test_read_only_role(self, use_org_level_role):
        """
        Test the read-only role (LibraryUserRole and its org-level equivalent)
        """
        # As staff user, add a block to self.library:
        block = self._add_simple_content_block()

        # Login as a non_staff_user:
        self._login_as_non_staff_user()
        self.assertFalse(self._can_access_library(self.library))

        block_url = reverse_usage_url('xblock_handler', block.location)

        def can_read_block():
            """ Check if studio lets us view the XBlock in the library """
            response = self.client.get_json(block_url)
            self.assertIn(response.status_code, (200, 403))  # 400 would be ambiguous
            return response.status_code == 200

        def can_edit_block():
            """ Check if studio lets us edit the XBlock in the library """
            response = self.client.ajax_post(block_url)
            self.assertIn(response.status_code, (200, 403))  # 400 would be ambiguous
            return response.status_code == 200

        def can_delete_block():
            """ Check if studio lets us delete the XBlock in the library """
            response = self.client.delete(block_url)
            self.assertIn(response.status_code, (200, 403))  # 400 would be ambiguous
            return response.status_code == 200

        def can_copy_block():
            """ Check if studio lets us duplicate the XBlock in the library """
            response = self.client.ajax_post(reverse_url('xblock_handler'), {
                'parent_locator': unicode(self.library.location),
                'duplicate_source_locator': unicode(block.location),
            })
            self.assertIn(response.status_code, (200, 403))  # 400 would be ambiguous
            return response.status_code == 200

        def can_create_block():
            """ Check if studio lets us make a new XBlock in the library """
            response = self.client.ajax_post(reverse_url('xblock_handler'), {
                'parent_locator': unicode(self.library.location), 'category': 'html',
            })
            self.assertIn(response.status_code, (200, 403))  # 400 would be ambiguous
            return response.status_code == 200

        # Check that we do not have read or write access to block:
        self.assertFalse(can_read_block())
        self.assertFalse(can_edit_block())
        self.assertFalse(can_delete_block())
        self.assertFalse(can_copy_block())
        self.assertFalse(can_create_block())

        # Give non_staff_user read-only permission:
        if use_org_level_role:
            OrgLibraryUserRole(self.lib_key.org).add_users(self.non_staff_user)
        else:
            LibraryUserRole(self.lib_key).add_users(self.non_staff_user)

        self.assertTrue(self._can_access_library(self.library))
        self.assertTrue(can_read_block())
        self.assertFalse(can_edit_block())
        self.assertFalse(can_delete_block())
        self.assertFalse(can_copy_block())
        self.assertFalse(can_create_block())

    @ddt.data(
        (LibraryUserRole, CourseStaffRole, True),
        (CourseStaffRole, CourseStaffRole, True),
        (None, CourseStaffRole, False),
        (LibraryUserRole, None, False),
    )
    @ddt.unpack
    def test_duplicate_across_courses(self, library_role, course_role, expected_result):
        """
        Test that the REST API will correctly allow/refuse when copying
        from a library with (write, read, or no) access to a course with (write or no) access.
        """
        # As staff user, add a block to self.library:
        block = self._add_simple_content_block()
        # And create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        self._login_as_non_staff_user()

        # Assign roles:
        if library_role:
            library_role(self.lib_key).add_users(self.non_staff_user)
        if course_role:
            course_role(course.location.course_key).add_users(self.non_staff_user)

        # Copy block to the course:
        response = self.client.ajax_post(reverse_url('xblock_handler'), {
            'parent_locator': unicode(course.location),
            'duplicate_source_locator': unicode(block.location),
        })
        self.assertIn(response.status_code, (200, 403))  # 400 would be ambiguous
        duplicate_action_allowed = (response.status_code == 200)
        self.assertEqual(duplicate_action_allowed, expected_result)

    @ddt.data(
        (LibraryUserRole, CourseStaffRole, True),
        (CourseStaffRole, CourseStaffRole, True),
        (None, CourseStaffRole, False),
        (LibraryUserRole, None, False),
    )
    @ddt.unpack
    def test_refresh_library_content_permissions(self, library_role, course_role, expected_result):
        """
        Test that the LibraryContent block's 'refresh_children' handler will correctly
        handle permissions and allow/refuse when updating its content with the latest
        version of a library. We try updating from a library with (write, read, or no)
        access to a course with (write or no) access.
        """
        # As staff user, add a block to self.library:
        self._add_simple_content_block()
        # And create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            course = CourseFactory.create()

        self._login_as_non_staff_user()

        # Assign roles:
        if library_role:
            library_role(self.lib_key).add_users(self.non_staff_user)
        if course_role:
            course_role(course.location.course_key).add_users(self.non_staff_user)

        # Try updating our library content block:
        lc_block = self._add_library_content_block(course, self.lib_key)
        # We must use the CMS's module system in order to get permissions checks.
        self._bind_module(lc_block, user=self.non_staff_user)
        lc_block = self._refresh_children(lc_block, status_code_expected=200 if expected_result else 403)
        self.assertEqual(len(lc_block.children), 1 if expected_result else 0)


class TestOverrides(LibraryTestCase):
    """
    Test that overriding block Scope.settings fields from a library in a specific course works
    """
    def setUp(self):
        super(TestOverrides, self).setUp()
        self.original_display_name = "A Problem Block"
        self.original_weight = 1

        # Create a problem block in the library:
        self.problem = ItemFactory.create(
            category="problem",
            parent_location=self.library.location,
            display_name=self.original_display_name,  # display_name is a Scope.settings field
            weight=self.original_weight,  # weight is also a Scope.settings field
            user_id=self.user.id,
            publish_item=False,
        )

        # Also create a course:
        with modulestore().default_store(ModuleStoreEnum.Type.split):
            self.course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        self.lc_block = self._add_library_content_block(self.course, self.lib_key)
        self.lc_block = self._refresh_children(self.lc_block)
        self.problem_in_course = modulestore().get_item(self.lc_block.children[0])

    def test_overrides(self):
        """
        Test that we can override Scope.settings values in a course.
        """
        new_display_name = "Modified Problem Title"
        new_weight = 10
        self.problem_in_course.display_name = new_display_name
        self.problem_in_course.weight = new_weight
        modulestore().update_item(self.problem_in_course, self.user.id)

        # Add a second LibraryContent block to the course, with no override:
        lc_block2 = self._add_library_content_block(self.course, self.lib_key)
        lc_block2 = self._refresh_children(lc_block2)
        # Re-load the two problem blocks - one with and one without an override:
        self.problem_in_course = modulestore().get_item(self.lc_block.children[0])
        problem2_in_course = modulestore().get_item(lc_block2.children[0])

        self.assertEqual(self.problem_in_course.display_name, new_display_name)
        self.assertEqual(self.problem_in_course.weight, new_weight)

        self.assertEqual(problem2_in_course.display_name, self.original_display_name)
        self.assertEqual(problem2_in_course.weight, self.original_weight)

    def test_reset_override(self):
        """
        If we override a setting and then reset it, we should get the library value.
        """
        new_display_name = "Modified Problem Title"
        new_weight = 10
        self.problem_in_course.display_name = new_display_name
        self.problem_in_course.weight = new_weight
        modulestore().update_item(self.problem_in_course, self.user.id)
        self.problem_in_course = modulestore().get_item(self.problem_in_course.location)

        self.assertEqual(self.problem_in_course.display_name, new_display_name)
        self.assertEqual(self.problem_in_course.weight, new_weight)

        # Reset:
        for field_name in ["display_name", "weight"]:
            self.problem_in_course.fields[field_name].delete_from(self.problem_in_course)

        # Save, reload, and verify:
        modulestore().update_item(self.problem_in_course, self.user.id)
        self.problem_in_course = modulestore().get_item(self.problem_in_course.location)

        self.assertEqual(self.problem_in_course.display_name, self.original_display_name)
        self.assertEqual(self.problem_in_course.weight, self.original_weight)

    def test_consistent_definitions(self):
        """
        Make sure that the new child of the LibraryContent block
        shares its definition with the original (self.problem).

        This test is specific to split mongo.
        """
        definition_id = self.problem.definition_locator.definition_id
        self.assertEqual(self.problem_in_course.definition_locator.definition_id, definition_id)

        # Now even if we change some Scope.settings fields and refresh, the definition should be unchanged
        self.problem.weight = 20
        self.problem.display_name = "NEW"
        modulestore().update_item(self.problem, self.user.id)
        self.lc_block = self._refresh_children(self.lc_block)
        self.problem_in_course = modulestore().get_item(self.problem_in_course.location)

        self.assertEqual(self.problem.definition_locator.definition_id, definition_id)
        self.assertEqual(self.problem_in_course.definition_locator.definition_id, definition_id)

    def test_persistent_overrides(self):
        """
        Test that when we override Scope.settings values in a course,
        the override values persist even when the block is refreshed
        with updated blocks from the library.
        """
        new_display_name = "Modified Problem Title"
        new_weight = 15
        self.problem_in_course.display_name = new_display_name
        self.problem_in_course.weight = new_weight

        modulestore().update_item(self.problem_in_course, self.user.id)
        self.problem_in_course = modulestore().get_item(self.problem_in_course.location)
        self.assertEqual(self.problem_in_course.display_name, new_display_name)
        self.assertEqual(self.problem_in_course.weight, new_weight)

        # Change the settings in the library version:
        self.problem.display_name = "X"
        self.problem.weight = 99
        new_data_value = "<problem><p>Changed data to check that non-overriden fields *do* get updated.</p></problem>"
        self.problem.data = new_data_value
        modulestore().update_item(self.problem, self.user.id)

        self.lc_block = self._refresh_children(self.lc_block)
        self.problem_in_course = modulestore().get_item(self.problem_in_course.location)

        self.assertEqual(self.problem_in_course.display_name, new_display_name)
        self.assertEqual(self.problem_in_course.weight, new_weight)
        self.assertEqual(self.problem_in_course.data, new_data_value)


class TestIncompatibleModuleStore(LibraryTestCase):
    """
    Tests for proper validation errors with an incompatible course modulestore.
    """
    def setUp(self):
        super(TestIncompatibleModuleStore, self).setUp()
        # Create a course in an incompatible modulestore.
        with modulestore().default_store(ModuleStoreEnum.Type.mongo):
            self.course = CourseFactory.create()

        # Add a LibraryContent block to the course:
        self.lc_block = self._add_library_content_block(self.course, self.lib_key)

    def test_incompatible_modulestore(self):
        """
        Verifies that, if a user is using a modulestore that doesn't support libraries,
        a validation error will be produced.
        """
        validation = self.lc_block.validate()
        self.assertEqual(validation.summary.type, validation.summary.ERROR)
        self.assertIn(
            "This course does not support content libraries.", validation.summary.text)
