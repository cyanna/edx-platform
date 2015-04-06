# -*- coding: utf-8 -*-
"""
End-to-end tests for the main LMS Dashboard (aka, Student Dashboard).
"""
from uuid import uuid4
from ..helpers import UniqueCourseTest
from ...fixtures.course import CourseFixture
from ...pages.lms.auto_auth import AutoAuthPage
from ...pages.lms.dashboard import DashboardPage
from ...pages.lms.login_and_register import CombinedLoginAndRegisterPage

class LmsDashboardPageTest(UniqueCourseTest):

    def setUp(self):
        """
        Initializes the components (page objects, courses, users) for this test suite
        """
        # Some parameters are provided by the parent setUp() routine, such as the following:
        # self.course_id, self.course_info, self.unique_id
        super(LmsDashboardPageTest, self).setUp()

        # Load page objects for use by the tests
        self.dashboard_page = DashboardPage(self.browser)
        self.login_page = CombinedLoginAndRegisterPage(
            self.browser,
            start_page="login",
            course_id=self.course_id
        )

        # Configure some aspects of the test course and install the settings into the course
        self.course_fixture = CourseFixture(
            self.course_info["org"],
            self.course_info["number"],
            self.course_info["run"],
            self.course_info["display_name"]
        ).install()

        # Create the test user, register them for the course, and authenticate
        self.username = "test_{uuid}".format(uuid=self.unique_id[0:6])
        self.email = "{user}@example.com".format(user=self.username)
        password = "password"
        AutoAuthPage(
            self.browser,
            username=self.username,
            email=self.email,
            course_id=self.course_id
         ).visit()

        # Navigate the authenticated, enrolled user to the dashboard page and get testing!
        self.dashboard_page.visit()

    def test_dashboard_course_listings(self):
        """
        Perform a general validation of the course listings section
        """
        course_listings = self.dashboard_page.get_course_listings()
        self.assertEqual(len(course_listings), 1)

    def test_dashboard_social_sharing_feature(self):
        """
        Validate the behavior of the social sharing feature
        """
        twitter_widget = self.dashboard_page.get_course_social_sharing_widget('twitter')
        twitter_url_prefix = "https://twitter.com/intent/tweet?text=Testing+feature%3A%20http%3A%2F%2Flocalhost%3A8003%2Fcourses%2F"
        self.assertEqual(twitter_widget.attrs('data-tooltip')[0], 'Share on Twitter')
        self.assertEqual(twitter_widget.attrs('aria-haspopup')[0], 'true')
        self.assertEqual(twitter_widget.attrs('aria-expanded')[0], 'false')
        self.assertIn(twitter_url_prefix, twitter_widget.attrs('href')[0])
        self.assertIn('%2Fabout', twitter_widget.attrs('href')[0])
        self.assertEqual(twitter_widget.attrs('target')[0], '_blank')
        self.assertEqual(twitter_widget.attrs('title')[0], 'Share on Twitter')
        self.assertIn(twitter_url_prefix, twitter_widget.attrs('onclick')[0])
        self.assertIn('%2Fabout', twitter_widget.attrs('onclick')[0])

        facebook_widget = self.dashboard_page.get_course_social_sharing_widget('facebook')
        facebook_url_prefix = "https://www.facebook.com/sharer/sharer.php?u=http%3A%2F%2Flocalhost%3A8003%2Fcourses%2F"
        self.assertEqual(facebook_widget.attrs('data-tooltip')[0], 'Share on Facebook')
        self.assertEqual(facebook_widget.attrs('aria-haspopup')[0], 'true')
        self.assertEqual(facebook_widget.attrs('aria-expanded')[0], 'false')
        self.assertIn(facebook_url_prefix, facebook_widget.attrs('href')[0])
        self.assertIn('%2Fabout', facebook_widget.attrs('href')[0])
        self.assertEqual(facebook_widget.attrs('target')[0], '_blank')
        self.assertEqual(facebook_widget.attrs('title')[0], 'Share on Facebook')
        self.assertIn(facebook_url_prefix, facebook_widget.attrs('onclick')[0])
        self.assertIn('%2Fabout', facebook_widget.attrs('onclick')[0])
