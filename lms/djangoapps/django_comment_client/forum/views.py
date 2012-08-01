from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.utils import simplejson
from django.core.context_processors import csrf
from django.core.urlresolvers import reverse

from mitxmako.shortcuts import render_to_response, render_to_string
from courseware.courses import check_course

from dateutil.tz import tzlocal
from datehelper import time_ago_in_words

from django_comment_client.utils import get_categorized_discussion_info, extract, strip_none
from urllib import urlencode

import json
import comment_client
import dateutil


THREADS_PER_PAGE = 20
PAGES_NEARBY_DELTA = 2

class HtmlResponse(HttpResponse):
    def __init__(self, html=''):
        super(HtmlResponse, self).__init__(html, content_type='text/plain')

def render_accordion(request, course, discussion_id):

    discussion_info = get_categorized_discussion_info(request, course)

    context = {
        'course': course,
        'discussion_info': discussion_info,
        'active': discussion_id,
        'csrf': csrf(request)['csrf_token'],
    }

    return render_to_string('discussion/_accordion.html', context)

def render_discussion(request, course_id, threads, discussion_id=None, with_search_bar=True, \
                      discussion_type='inline', query_params={}):

    template = {
        'inline': 'discussion/_inline.html',
        'forum': 'discussion/_forum.html',
    }[discussion_type]

    base_url = {
        'inline': (lambda: reverse('django_comment_client.forum.views.inline_discussion', args=[course_id, discussion_id])), 
        'forum': (lambda: reverse('django_comment_client.forum.views.forum_form_discussion', args=[course_id, discussion_id])),
    }[discussion_type]()

    context = {
        'threads': threads,
        'discussion_id': discussion_id,
        'search_bar': '' if not with_search_bar \
                      else render_search_bar(request, course_id, discussion_id, text=query_params.get('text', '')),
        'user_info': comment_client.get_user_info(request.user.id, raw=True),
        'course_id': course_id,
        'request': request,
        'pages_nearby_delta': PAGES_NEARBY_DELTA,
        'discussion_type': discussion_type,
        'base_url': base_url,
        'query_params': strip_none(extract(query_params, ['page', 'sort_key', 'sort_order', 'tags', 'text'])),
    }
    context = dict(context.items() + query_params.items())
    return render_to_string(template, context)

def render_inline_discussion(*args, **kwargs):
    return render_discussion(discussion_type='inline', *args, **kwargs)

def render_forum_discussion(*args, **kwargs):
    return render_discussion(discussion_type='forum', *args, **kwargs)

def get_threads(request, course_id, discussion_id):
    query_params = {
        'page': request.GET.get('page', 1),
        'per_page': THREADS_PER_PAGE, #TODO maybe change this later
        'sort_key': request.GET.get('sort_key', None),
        'sort_order': request.GET.get('sort_order', None),
        'text': request.GET.get('text', None), 
        'tags': request.GET.get('tags', None),
    }

    if query_params['text'] or query_params['tags']: #TODO do tags search without sunspot
        query_params['commentable_id'] = discussion_id
        threads, page, num_pages = comment_client.search_threads(course_id, recursive=False, query_params=query_params)
    else:
        threads, page, num_pages = comment_client.get_threads(discussion_id, recursive=False, query_params=query_params)

    query_params['page'] = page
    query_params['num_pages'] = num_pages

    return threads, query_params

# discussion per page is fixed for now
def inline_discussion(request, course_id, discussion_id):
    threads, query_params = get_threads(request, course_id, discussion_id)
    html = render_inline_discussion(request, course_id, threads, discussion_id=discussion_id,  \
                                                                 query_params=query_params)
    return HtmlResponse(html)

def render_search_bar(request, course_id, discussion_id=None, text=''):
    if not discussion_id:
        return ''
    context = {
        'discussion_id': discussion_id,
        'text': text,
        'course_id': course_id,
    }
    return render_to_string('discussion/_search_bar.html', context)

def forum_form_discussion(request, course_id, discussion_id):
    course = check_course(course_id)
    threads, query_params = get_threads(request, course_id, discussion_id)
    content = render_forum_discussion(request, course_id, threads, discussion_id=discussion_id, \
                                                                   query_params=query_params)
    context = {
        'csrf': csrf(request)['csrf_token'],
        'course': course,
        'content': content,
        'accordion': render_accordion(request, course, discussion_id),
    }
    return render_to_response('discussion/index.html', context)

def render_single_thread(request, course_id, thread_id):
    def get_annotated_content_info(thread, user_id):
        infos = {}
        def _annotate(content):
            infos[str(content['id'])] = {
                'editable': str(content['user_id']) == str(user_id), # TODO may relax this to instructors
            }
            for child in content['children']:
                _annotate(child)
        _annotate(thread)
        return infos

    thread = comment_client.get_thread(thread_id, recursive=True)

    context = {
        'thread': thread,
        'user_info': comment_client.get_user_info(request.user.id, raw=True),
        'annotated_content_info': json.dumps(get_annotated_content_info(thread=thread, user_id=request.user.id)),
        'course_id': course_id,
        'request': request,
    }
    return render_to_string('discussion/_single_thread.html', context)

def single_thread(request, course_id, discussion_id, thread_id):

    course = check_course(course_id)

    context = {
        'csrf': csrf(request)['csrf_token'],
        'init': '',
        'content': render_single_thread(request, course_id, thread_id),
        'accordion': render_accordion(request, course, discussion_id),
        'course': course,
    }

    return render_to_response('discussion/index.html', context)

def search(request, course_id):

    course = check_course(course_id)

    text = request.GET.get('text', None)
    commentable_id = request.GET.get('commentable_id', None)
    tags = request.GET.get('tags', None)

    threads = comment_client.search_threads({
        'text': text,
        'commentable_id': commentable_id,
        'tags': tags,
    })

    context = {
        'csrf': csrf(request)['csrf_token'],
        'init': '',
        'content': render_forum_discussion(request, course_id, threads, search_text=text),
        'accordion': '',
        'course': course,
    }

    return render_to_response('discussion/index.html', context)
