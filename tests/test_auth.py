import httplib2
import tests
from six.moves import urllib


def test_credentials():
    c = httplib2.Credentials()
    c.add('joe', 'password')
    assert tuple(c.iter('bitworking.org'))[0] == ('joe', 'password')
    assert tuple(c.iter(''))[0] == ('joe', 'password')
    c.add('fred', 'password2', 'wellformedweb.org')
    assert tuple(c.iter('bitworking.org'))[0] == ('joe', 'password')
    assert len(tuple(c.iter('bitworking.org'))) == 1
    assert len(tuple(c.iter('wellformedweb.org'))) == 2
    assert ('fred', 'password2') in tuple(c.iter('wellformedweb.org'))
    c.clear()
    assert len(tuple(c.iter('bitworking.org'))) == 0
    c.add('fred', 'password2', 'wellformedweb.org')
    assert ('fred', 'password2') in tuple(c.iter('wellformedweb.org'))
    assert len(tuple(c.iter('bitworking.org'))) == 0
    assert len(tuple(c.iter(''))) == 0


def test_auth_basic():
    # Test Basic Authentication
    http = httplib2.Http()
    password = tests.gen_password()
    handler = tests.http_reflect_with_auth(allow_scheme='basic', allow_credentials=(('joe', password),))
    with tests.server_request(handler, request_count=3) as uri:
        response, content = http.request(uri, 'GET')
        assert response.status == 401
        http.add_credentials('joe', password)
        response, content = http.request(uri, 'GET')
        assert response.status == 200


def test_auth_basic_for_domain():
    # Test Basic Authentication
    http = httplib2.Http()
    password = tests.gen_password()
    handler = tests.http_reflect_with_auth(allow_scheme='basic', allow_credentials=(('joe', password),))
    with tests.server_request(handler, request_count=4) as uri:
        response, content = http.request(uri, 'GET')
        assert response.status == 401
        http.add_credentials('joe', password, 'example.org')
        response, content = http.request(uri, 'GET')
        assert response.status == 401
        domain = urllib.parse.urlparse(uri)[1]
        http.add_credentials('joe', password, domain)
        response, content = http.request(uri, 'GET')
        assert response.status == 200


def test_auth_basic_two_credentials():
    # Test Basic Authentication with multiple sets of credentials
    http = httplib2.Http()
    password1 = tests.gen_password()
    password2 = tests.gen_password()
    allowed = [('joe', password1)]  # exploit shared mutable list
    handler = tests.http_reflect_with_auth(allow_scheme='basic', allow_credentials=allowed)
    with tests.server_request(handler, request_count=7) as uri:
        http.add_credentials('fred', password2)
        response, content = http.request(uri, 'GET')
        assert response.status == 401
        http.add_credentials('joe', password1)
        response, content = http.request(uri, 'GET')
        assert response.status == 200
        allowed[0] = ('fred', password2)
        response, content = http.request(uri, 'GET')
        assert response.status == 200


def test_auth_digest():
    # Test that we support Digest Authentication
    http = httplib2.Http()
    password = tests.gen_password()
    handler = tests.http_reflect_with_auth(allow_scheme='digest', allow_credentials=(('joe', password),))
    with tests.server_request(handler, request_count=3) as uri:
        response, content = http.request(uri, 'GET')
        assert response.status == 401
        http.add_credentials('joe', password)
        response, content = http.request(uri, 'GET')
        assert response.status == 200, content


def test_auth_digest_next_nonce_nc():
    # Test that if the server sets nextnonce that we reset
    # the nonce count back to 1
    http = httplib2.Http()
    password = tests.gen_password()
    handler = tests.http_reflect_with_auth(allow_scheme='digest', allow_credentials=(('joe', password),))
    with tests.server_request(handler, request_count=4) as uri:
        http.add_credentials('joe', password)
        response, content = http.request(uri, 'GET')
        info = httplib2._parse_www_authenticate(response, 'authentication-info')
        assert info.get('nc') == 0, repr(response)
        assert response.status == 200
        response, content = http.request(uri, 'GET')
        info2 = httplib2._parse_www_authenticate(response, 'authentication-info')
        assert response.status == 200
        assert 'nextnonce' in info
        assert info2.get('nc') == 1, info2


def test_DigestAuthStale():
    # Test that we can handle a nonce becoming stale
    uri = urllib.parse.urljoin(base, 'digest-expire/file.txt')
    http.add_credentials('joe', 'password')
    response, content = http.request(uri, 'GET', headers = {'cache-control':'no-cache'})
    info = httplib2._parse_www_authenticate(response, 'authentication-info')
    assert response.status == 200

    time.sleep(3)
    # Sleep long enough that the nonce becomes stale

    response, content = http.request(uri, 'GET', headers = {'cache-control':'no-cache'})
    assert not response.fromcache
    assert response._stale_digest
    info3 = httplib2._parse_www_authenticate(response, 'authentication-info')
    assert response.status == 200


def test_ParseWWWAuthenticateEmpty():
    res = httplib2._parse_www_authenticate({})
    assertEqual(len(list(res.keys())), 0)


def test_ParseWWWAuthenticate():
    # different uses of spaces around commas
    res = httplib2._parse_www_authenticate({ 'www-authenticate': 'Test realm="test realm" , foo=foo ,bar="bar", baz=baz,qux=qux'})
    assertEqual(len(list(res.keys())), 1)
    assertEqual(len(list(res['test'].keys())), 5)

    # tokens with non-alphanum
    res = httplib2._parse_www_authenticate({ 'www-authenticate': 'T*!%#st realm=to*!%#en, to*!%#en="quoted string"'})
    assertEqual(len(list(res.keys())), 1)
    assertEqual(len(list(res['t*!%#st'].keys())), 2)

    # quoted string with quoted pairs
    res = httplib2._parse_www_authenticate({ 'www-authenticate': 'Test realm="a \\"test\\" realm"'})
    assertEqual(len(list(res.keys())), 1)
    assert res['test']['realm'] == 'a "test" realm'


def test_ParseWWWAuthenticateStrict():
    httplib2.USE_WWW_AUTH_STRICT_PARSING = 1
    test_ParseWWWAuthenticate()
    httplib2.USE_WWW_AUTH_STRICT_PARSING = 0


def test_ParseWWWAuthenticateBasic():
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Basic realm="me"'})
    basic = res['basic']
    assert 'me' == basic['realm']

    res = httplib2._parse_www_authenticate({'www-authenticate': 'Basic realm="me", algorithm="MD5"'})
    basic = res['basic']
    assert 'me' == basic['realm']
    assert 'MD5' == basic['algorithm']

    res = httplib2._parse_www_authenticate({'www-authenticate': 'Basic realm="me", algorithm=MD5'})
    basic = res['basic']
    assert 'me' == basic['realm']
    assert 'MD5' == basic['algorithm']


def test_ParseWWWAuthenticateBasic2():
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Basic realm="me",other="fred" '})
    basic = res['basic']
    assert 'me' == basic['realm']
    assert 'fred' == basic['other']


def test_ParseWWWAuthenticateBasic3():
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Basic REAlm="me" '})
    basic = res['basic']
    assert 'me' == basic['realm']


def test_ParseWWWAuthenticateDigest():
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Digest realm="testrealm@host.com", qop="auth,auth-int", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", opaque="5ccc069c403ebaf9f0171e9517f40e41"'})
    digest = res['digest']
    assertEqual('testrealm@host.com', digest['realm'])
    assertEqual('auth,auth-int', digest['qop'])


def test_ParseWWWAuthenticateMultiple():
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Digest realm="testrealm@host.com", qop="auth,auth-int", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", opaque="5ccc069c403ebaf9f0171e9517f40e41" Basic realm="me" '})
    digest = res['digest']
    assertEqual('testrealm@host.com', digest['realm'])
    assertEqual('auth,auth-int', digest['qop'])
    assert 'dcd98b7102dd2f0e8b11d0f600bfb0c093' == digest['nonce']
    assert '5ccc069c403ebaf9f0171e9517f40e41' == digest['opaque']
    basic = res['basic']
    assert 'me' == basic['realm']


def test_ParseWWWAuthenticateMultiple2():
    # Handle an added comma between challenges, which might get thrown in if the challenges were
    # originally sent in separate www-authenticate headers.
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Digest realm="testrealm@host.com", qop="auth,auth-int", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", opaque="5ccc069c403ebaf9f0171e9517f40e41", Basic realm="me" '})
    digest = res['digest']
    assertEqual('testrealm@host.com', digest['realm'])
    assertEqual('auth,auth-int', digest['qop'])
    assert 'dcd98b7102dd2f0e8b11d0f600bfb0c093' == digest['nonce']
    assert '5ccc069c403ebaf9f0171e9517f40e41' == digest['opaque']
    basic = res['basic']
    assert 'me' == basic['realm']


def test_ParseWWWAuthenticateMultiple3():
    # Handle an added comma between challenges, which might get thrown in if the challenges were
    # originally sent in separate www-authenticate headers.
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Digest realm="testrealm@host.com", qop="auth,auth-int", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", opaque="5ccc069c403ebaf9f0171e9517f40e41", Basic realm="me", WSSE realm="foo", profile="UsernameToken"'})
    digest = res['digest']
    assertEqual('testrealm@host.com', digest['realm'])
    assertEqual('auth,auth-int', digest['qop'])
    assert 'dcd98b7102dd2f0e8b11d0f600bfb0c093' == digest['nonce']
    assert '5ccc069c403ebaf9f0171e9517f40e41' == digest['opaque']
    basic = res['basic']
    assert 'me' == basic['realm']
    wsse = res['wsse']
    assert 'foo' == wsse['realm']
    assert 'UsernameToken' == wsse['profile']


def test_ParseWWWAuthenticateMultiple4():
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Digest realm="test-real.m@host.com", qop \t=\t"\tauth,auth-int", nonce="(*)&^&$%#",opaque="5ccc069c403ebaf9f0171e9517f40e41", Basic REAlm="me", WSSE realm="foo", profile="UsernameToken"'})
    digest = res['digest']
    assertEqual('test-real.m@host.com', digest['realm'])
    assertEqual('\tauth,auth-int', digest['qop'])
    assertEqual('(*)&^&$%#', digest['nonce'])


def test_ParseWWWAuthenticateMoreQuoteCombos():
    res = httplib2._parse_www_authenticate({'www-authenticate': 'Digest realm="myrealm", nonce="Ygk86AsKBAA=3516200d37f9a3230352fde99977bd6d472d4306", algorithm=MD5, qop="auth", stale=true'})
    digest = res['digest']
    assert 'myrealm' == digest['realm']


def test_ParseWWWAuthenticateMalformed():
    with tests.assert_raises(httplib2.MalformedHeader):
        httplib2._parse_www_authenticate(
            {'www-authenticate': 'OAuth "Facebook Platform" "invalid_token" "Invalid OAuth access token."'}
        )


def test_DigestObject():
    credentials = ('joe', 'password')
    host = None
    request_uri = '/projects/httplib2/test/digest/'
    headers = {}
    response = {
        'www-authenticate': 'Digest realm="myrealm", nonce="Ygk86AsKBAA=3516200d37f9a3230352fde99977bd6d472d4306", algorithm=MD5, qop="auth"'
    }
    content = b''

    d = httplib2.DigestAuthentication(credentials, host, request_uri, headers, response, content, None)
    d.request('GET', request_uri, headers, content, cnonce="33033375ec278a46")
    our_request = 'authorization: ' + headers['authorization']
    working_request = 'authorization: Digest username="joe", realm="myrealm", nonce="Ygk86AsKBAA=3516200d37f9a3230352fde99977bd6d472d4306", uri="/projects/httplib2/test/digest/", algorithm=MD5, response="97ed129401f7cdc60e5db58a80f3ea8b", qop=auth, nc=00000001, cnonce="33033375ec278a46"'
    assert our_request == working_request


def test_DigestObjectWithOpaque():
    credentials = ('joe', 'password')
    host = None
    request_uri = '/projects/httplib2/test/digest/'
    headers = {}
    response = {
        'www-authenticate': 'Digest realm="myrealm", nonce="Ygk86AsKBAA=3516200d37f9a3230352fde99977bd6d472d4306", algorithm=MD5, qop="auth", opaque="atestopaque"'
    }
    content = ''

    d = httplib2.DigestAuthentication(credentials, host, request_uri, headers, response, content, None)
    d.request('GET', request_uri, headers, content, cnonce="33033375ec278a46")
    our_request = 'authorization: ' + headers['authorization']
    working_request = 'authorization: Digest username="joe", realm="myrealm", nonce="Ygk86AsKBAA=3516200d37f9a3230352fde99977bd6d472d4306", uri="/projects/httplib2/test/digest/", algorithm=MD5, response="97ed129401f7cdc60e5db58a80f3ea8b", qop=auth, nc=00000001, cnonce="33033375ec278a46", opaque="atestopaque"'
    assert our_request == working_request


def test_DigestObjectStale():
    credentials = ('joe', 'password')
    host = None
    request_uri = '/projects/httplib2/test/digest/'
    headers = {}
    response = httplib2.Response({})
    response['www-authenticate'] = 'Digest realm="myrealm", nonce="Ygk86AsKBAA=3516200d37f9a3230352fde99977bd6d472d4306", algorithm=MD5, qop="auth", stale=true'
    response.status = 401
    content = b''
    d = httplib2.DigestAuthentication(credentials, host, request_uri, headers, response, content, None)
    # Returns true to force a retry
    assert d.response(response, content)


def test_DigestObjectAuthInfo():
    credentials = ('joe', 'password')
    host = None
    request_uri = '/projects/httplib2/test/digest/'
    headers = {}
    response = httplib2.Response({})
    response['www-authenticate'] = 'Digest realm="myrealm", nonce="Ygk86AsKBAA=3516200d37f9a3230352fde99977bd6d472d4306", algorithm=MD5, qop="auth", stale=true'
    response['authentication-info'] = 'nextnonce="fred"'
    content = b''
    d = httplib2.DigestAuthentication(credentials, host, request_uri, headers, response, content, None)
    # Returns true to force a retry
    assert not d.response(response, content)
    assert 'fred' == d.challenge['nonce']
    assert 1 == d.challenge['nc']


def test_WsseAlgorithm():
    digest = httplib2._wsse_username_token('d36e316282959a9ed4c89851497a717f', '2003-12-15T14:43:07Z', 'taadtaadpstcsm')
    expected = b'quR/EWLAV4xLf9Zqyw4pDmfV9OY='
    assert expected == digest