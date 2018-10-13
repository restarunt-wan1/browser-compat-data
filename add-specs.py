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


def getSpecsArray(mdn_url, sectionname, spec_urls, http):
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
        specs = []
        for row in rows:
            hrefs = row.xpath('td[1]/a/@href')
            if not(hrefs):
                continue
            spec_url = hrefs[0].strip()
            if not(urlparse(spec_url).fragment):
                alarm(mdn_url + ' has spec URL with no fragment: ' + spec_url)
                continue
            if not(urlparse(spec_url).hostname):
                alarm(mdn_url + ' has spec URL with no hostname: ' + spec_url)
                continue
            spec_name = ''
            for base_url in spec_urls:
                if spec_url.startswith(base_url):
                    spec_name = spec_urls[base_url]['name']
            cprint('Adding %s (%s)' % (spec_url, spec_name), 'green')
            spec = OrderedDict()
            spec['name'] = spec_name
            spec['url'] = spec_url
            specs.append(spec)
        return specs
    except Exception, e:
        sys.stderr.write('Something went wrong: %s\n' % str(e))
        return []


def walkBaseData(basedata, filename, spec_urls, http, basename, sectionname,
                 bcd_data):
    for featurename in basedata:
        feature_data = basedata[featurename]
        path = '%s.%s.%s' % (sectionname, basename, featurename)
        bcd_data[sectionname][basename][featurename] = \
            processTarget(feature_data, filename, spec_urls, http, path)
        for subfeaturename in feature_data:
            subfeaturedata = feature_data[subfeaturename]
            path = '%s.%s.%s.%s' % (sectionname, basename, featurename,
                                    subfeaturename)
            bcd_data[sectionname][basename][featurename][subfeaturename] = \
                processTarget(subfeaturedata, filename, spec_urls, http, path)


def processTarget(target, filename, spec_urls, http, path):
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
        if 'specs' in target_data:
            if not(len(sys.argv) > 1 and sys.argv[1] == 'fullupdate'):
                return target
        mdn_url = target_data['mdn_url']
        specs = getSpecsArray(mdn_url, 'Specifications', spec_urls, http)
        if not(specs):
            specs = getSpecsArray(mdn_url, 'Specification', spec_urls, http)
        if not(specs):
            return target
        target['__compat']['specs'] = specs
    except TypeError:
        pass
    return target


def main():
    http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED',
                               ca_certs=certifi.where())
    response = http.request('GET', 'https://raw.githubusercontent.com/mdn/' +
                            'kumascript/master/macros/SpecData.json')
    spec_data = json.loads(response.data, object_pairs_hook=OrderedDict)
    spec_urls = {}
    for spec_name in spec_data:
        url = spec_data[spec_name]['url']
        spec_urls[url] = {}
        spec_urls[url]['name'] = spec_name
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
                        processTarget(basedata, filename, spec_urls, http, path)
                    if basedata:
                        walkBaseData(basedata, filename, spec_urls, http,
                                     basename, sectionname, bcd_data)
            f.seek(0)
            f.write(unicode(json.dumps(bcd_data, indent=2,
                                       separators=(',', ': '),
                                       ensure_ascii=False) + '\n'))
            f.truncate()
            f.close()


main()
