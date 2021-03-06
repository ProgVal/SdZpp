# -*- coding: utf8 -*-

###
# Copyright (c) 2011, Valentin Lorentz
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###


import re
import urllib
import urllib2
import feedparser

from django.http import Http404
from django.http import HttpResponse

from sdzpp.common.templates import render_template
from phone.common import *

regexp_html_tag = re.compile(r'<.*?>')
regexp_id_in_news_link = re.compile(r'http://www.siteduzero.com/news-62-(?P<id>[0-9]+)-.*.html')
regexp_h1 = re.compile(r'<h1>(?P<title>.*)</h1>')
regexp_news_logo = re.compile(r'<img( alt="")? src="(?P<url>http://uploads.siteduzero.com/[^"]+)"( alt="")? />(?P<content>.*)')
regexp_start_news_comments = re.compile(r'<table class="liste_messages">')
regexp_comments_page_link = re.compile(r'<a href=".*.html#discussion">(?P<id>[0-9]+)</a>')
regexp_comments_current_page_link = re.compile(r'<span class="rouge">[0-9]+</span>')
regexp_start_comment = re.compile(r'.*<div class="message_txt">(?P<message>.*)$')

def _index(request):
    feed = feedparser.parse('http://www.siteduzero.com/Templates/xml/news_fr.xml')
    news_list = []
    for entry in feed['entries']:
        news = Empty()
        content = entry['summary_detail']['value']
        matched = regexp_news_logo.match(content)
        assert matched is not None
        news.logo = matched.group('url')
        news.content = matched.group('content')
        news.short = regexp_html_tag.sub('', news.content)[0:140]
        news.id = regexp_id_in_news_link.match(entry['id']).group('id')
        news.title = entry['title_detail']['value']
        news_list.append(news)
    return {'news_list': news_list}

def index(request, **kwargs):
    return HttpResponse(render_template('phone/news/list.html', request,
                        _index(request, **kwargs)))

def _show(request, news_id):
    opener = UrlOpener()
    response = opener.open('http://www.siteduzero.com/news-62-%s-foo.html' % news_id)
    lines = response.read().split('\n')
    contributors = []
    content = ''
    title = None
    stage = 0
    for line in lines:
        if stage == 0:
            matched = regexp_h1.match(line)
            if matched is None:
                continue
            else:
                title = matched.group('title')
                stage = 1
        elif (stage == 1 or stage == 1.5) and '</div>' in line:
            stage += 0.5
        elif stage == 1 or stage == 1.5:
            matched = regexp_member_link.search(line)
            if matched is None:
                continue
            else:
                contributors.append(Member(matched))
        elif stage == 2 and '<div class="contenu_news">' in line:
            stage = 3
        elif stage == 3 and line == '<div class="taille_news" ' \
                                    'style="margin-bottom: 15px;">':
            break
        elif stage == 3 and '<div class="auteur_date_commentaires">' in line:
            break
        elif stage == 3:
            content += line + '\n'
    content = content[0:-len('</div>\n')]
    content = zcode_parser(content)
    return {'title': title, 'contributors': contributors,
            'content': content}

def show(request, **kwargs):
    return HttpResponse(render_template('phone/news/view.html', request,
                        _show(request, **kwargs)))

def _show_comments(request, news_id, page):
    opener = UrlOpener()
    response = opener.open('http://www.siteduzero.com/news-62-%s-p%s-foo.html'%
                           (news_id, page))
    lines = response.read().split('\n')
    stage = 0
    title = ''
    page_ids = []
    messages = []
    currentMessage = None
    for line in lines:
        if stage == 0:
            matched = regexp_h1.match(line)
            if matched is None:
                continue
            else:
                title = matched.group('title')
                stage = 1
        if stage == 1:
            matched = regexp_start_news_comments.search(line)
            if matched is not None:
                stage = 2
            else:
                continue
        elif stage == 2:
            matched = regexp_comments_page_link.search(line)
            matched_current = regexp_comments_current_page_link.search(line)
            if matched is not None:
                page_ids.append(matched.group('id'))
            elif matched_current is not None:
                page_ids.append(page)
            elif '<a href="' in line and 'Précedente' not in line \
                    and 'Suivante' not in line:
                page_ids.append('...')
            elif '</td>' in line:
                stage = 3
        elif stage == 3:
            if '<div id="footer">' in line:
                break
            if currentMessage is None:
                matched = regexp_member_link.search(line)
                if matched is None:
                    continue
                else:
                    currentMessage = Empty()
                    currentMessage.author = Member(matched)
            elif 'Posté ' in line and not hasattr(currentMessage, 'posted_on'):
                currentMessage.posted_on = line[len('\t\t\t\tPosté '):]
            elif not hasattr(currentMessage, 'content'):
                matched = regexp_start_comment.search(line)
                if matched is None:
                    continue
                else:
                    currentMessage.content = matched.group('message')
            elif '<div class="signature">' in line:
                currentMessage.content = currentMessage.content[:-len('</div>\n\t\t ')]
                currentMessage.content = zcode_parser(currentMessage.content)
                messages.append(currentMessage)
                currentMessage = None
            elif '<tr class="header_message">' in line: # No signature
                currentMessage.content = currentMessage.content[:-len('</div></div>'
                                                '\n\t\t\t\t</td>\n\t</tr>\n')]
                currentMessage.content = zcode_parser(currentMessage.content)
                messages.append(currentMessage)
                currentMessage = None
            else:
                currentMessage.content += line + '\n'
    return {'title': title, 'page_id': page, 'page_ids': page_ids,
            'comments': messages}

def show_comments(request, **kwargs):
    return HttpResponse(render_template('phone/news/view_comments.html', request,
                        _show_comments(request, **kwargs)))




