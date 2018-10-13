#!/usr/bin/env python2
import certifi
import io
import json
import os.path
import sys
import time
import urllib3
from collections import OrderedDict
from lxml.html import parse
from termcolor import cprint
from urlparse import urlparse


def alarm(message):
    cprint('Alarm: %s' % message, 'red', attrs=['bold'])


def getAdjustedSpecURL(url):
    if url.startswith('http://drafts.csswg.org/css-scoping/'):
        return url.replace('http://drafts.csswg', 'https://drafts.csswg')
    if url.startswith('https://drafts.csswg.org/css-logical-props/'):
        return url.replace('/css-logical-props/', '/css-logical/')
    if url.startswith('https://www.w3.org/TR/xpath-20/'):
        return url.replace('/TR/xpath-20/', '/TR/xpath20/')
    if url.startswith('https://w3c.github.io/input-events/index.html'):
        return url.replace('/input-events/index.html', '/input-events/')
    if url.startswith('https://w3c.github.io/webappsec-csp/embedded/'):
        return url.replace('/webappsec-csp/embedded/', '/webappsec-cspee/')
    if url.startswith('https://wicg.github.io/media-capabilities#'):
        return url.replace('/media-capabilities#', '/media-capabilities/#')
    if url.startswith('https://dev.w3.org/geo/api/spec-source.html'):
        return url.replace('https://dev.w3.org/geo/api/spec-source.html',
                           'https://www.w3.org/TR/geolocation-API/')
    if '/deviceorientation/spec-source-orientation.html' in url:
        return url.replace('spec-source-orientation.html', '')
    if 'spec.whatwg.org#' in url:
        return url.replace('spec.whatwg.org#', 'spec.whatwg.org/#')
    return url


def isObsolete(url):
    if url.startswith('https://www.w3.org/TR/REC-DOM-Level-1/'):
        return True
    if url.startswith('https://www.w3.org/TR/DOM-Level-2-'):
        return True
    if url.startswith('https://www.w3.org/TR/DOM-Level-3-Core/'):
        return True
    if url.startswith('https://www.w3.org/TR/ElementTraversal/'):
        return True
    if url.startswith('https://www.w3.org/TR/selectors-api/'):
        return True
    if url.startswith('https://dev.w3.org/2006/webapi/selectors-api2'):
        return True
    if url.startswith('https://w3c.github.io/webcomponents/spec/shadow/'):
        return True
    if url.startswith('https://w3c.github.io/staticrange/'):
        return True
    if url.startswith('https://www.w3.org/TR/dom/'):
        return True
    if url.startswith('https://w3c.github.io/microdata/'):
        return True
    if url.startswith('https://www.w3.org/TR/html5'):
        return True
    if url.startswith('https://www.ecma-international.org/'):
        return True
    if url.startswith('https://www.w3.org/TR/CSS1/'):
        return True
    if 'html401' in url:
        return True
    if 'developer.apple.com/library/safari' in url:
        return True
    if 'https://www.w3.org/TR/2014/WD-DOM-Level-3-Events-20140925/' in url:
        return True
    return False


def getSpecURLsArray(mdn_url, sectionname, http):
    url = 'https://developer.mozilla.org' + urlparse(mdn_url).path + \
        '?raw&macros&section=' + sectionname
    print 'Trying %s' % url
    response = http.request('GET', url)
    if response.status == 404:
        return []
    if response.status > 499:
        sys.stderr.write('50x for %s. Will retry after 60s...\n' % url)
        time.sleep(61)
        print 'Retrying %s' % url
        response = http.request('GET', url)
        if response.status == 404:
            return []
        if response.status > 499:
            sys.stderr.write('50x for %s. Giving up.\n' % url)
            return []
    html = response.data.decode('utf-8')
    if html == '':
        return []
    try:
        doc = parse(io.StringIO(unicode(html)))
        rows = doc.xpath('//table[1]//tr[td]')
        if not(rows):
            return []
        spec_urls = []
        has_spec_url = False
        for row in rows:
            hrefs = row.xpath('td[1]/a/@href')
            if not(hrefs):
                continue
            spec_url = hrefs[0].strip()
            if isObsolete(spec_url):
                continue
            if not(urlparse(spec_url).fragment):
                alarm(mdn_url + ' has spec URL with no fragment: ' + spec_url)
                continue
            if not(urlparse(spec_url).hostname):
                alarm(mdn_url + ' has spec URL with no hostname: ' + spec_url)
                continue
            if has_spec_url:
                cprint('Note:  ' + mdn_url + ' has multiple spec URLs', 'cyan')
            spec_url = getAdjustedSpecURL(spec_url)
            cprint('Adding %s' % (spec_url), 'green')
            spec_urls.append(spec_url)
            has_spec_url = True
        return spec_urls
    except Exception, e:
        sys.stderr.write('Something went wrong: %s\n' % str(e))
        return []


def walkBaseData(basedata, filename, http, basename, sectionname,
                 bcd_data):
    for featurename in basedata:
        feature_data = basedata[featurename]
        path = '%s.%s.%s' % (sectionname, basename, featurename)
        bcd_data[sectionname][basename][featurename] = \
            processTarget(feature_data, filename, http, path)
        for subfeaturename in feature_data:
            subfeaturedata = feature_data[subfeaturename]
            path = '%s.%s.%s.%s' % (sectionname, basename, featurename,
                                    subfeaturename)
            bcd_data[sectionname][basename][featurename][subfeaturename] = \
                processTarget(subfeaturedata, filename, http, path)


def processTarget(target, filename, http, path):
    try:
        if not('__compat' in target):
            return target
        target_data = target['__compat']
        if not('mdn_url' in target_data):
            if '_' not in path:
                alarm('%s in %s has no mdn_url' % (path, filename))
            return target
        if target_data['status']['deprecated']:
            return target
        if 'spec_urls' in target_data:
            if not(len(sys.argv) > 1 and sys.argv[1] == 'fullupdate'):
                return target
            else:
                del target['__compat']['spec_urls']
        mdn_url = target_data['mdn_url']
        spec_urls = getSpecURLsArray(mdn_url, 'Specifications', http)
        if not(spec_urls):
            spec_urls = getSpecURLsArray(mdn_url, 'Specification', http)
        if not(spec_urls):
            return target
        target['__compat']['spec_urls'] = spec_urls
    except TypeError:
        pass
    return target


def main():
    http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED',
                               ca_certs=certifi.where())
    dirnames = \
        [
            'api',
            'css',
            'html',
            'http',
            'javascript',
            'mathml',
            'svg',
            'webdriver',
            'xpath',
            'xslt'
        ]
    for dirname in dirnames:
        files = [os.path.join(dirpath, filename)
                 for (dirpath, dirs, files)
                 in os.walk(dirname)
                 for filename in (dirs + files)]
        files.sort()
        for filename in files:
            if os.path.splitext(filename)[1] != '.json':
                continue
            f = io.open(filename, 'r+', encoding='utf-8')
            bcd_data = json.load(f, object_pairs_hook=OrderedDict)
            for sectionname in bcd_data:
                for basename in bcd_data[sectionname]:
                    basedata = bcd_data[sectionname][basename]
                    path = '%s.%s' % (sectionname, basename)
                    path = sectionname + '.' + basename
                    bcd_data[sectionname][basename] = \
                        processTarget(basedata, filename, http, path)
                    if basedata:
                        walkBaseData(basedata, filename, http, basename,
                                     sectionname, bcd_data)
            f.seek(0)
            f.write(unicode(json.dumps(bcd_data, indent=2,
                                       separators=(',', ': '),
                                       ensure_ascii=False) + '\n'))
            f.truncate()
            f.close()


main()
