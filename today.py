import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib

# Fine-grained personal access token with All Repositories access:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Issues, read:Metadata, read:Pull Requests
# Issues and pull requests permissions not needed at the moment, but may be used in the future
#
# NOTE: a fine-grained token is scoped to a single resource owner, so one owned by GitJamieK
# cannot read private repos owned by an organization — those silently drop out of the stats.
# To count private org repos, either use a classic token (scopes: repo, read:org, read:user),
# or add a second fine-grained token whose resource owner is the org and which the org approved.
HEADERS = {'authorization': 'token '+ os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME'] # e.g. 'GitJamieK'
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0, 'recursive_loc': 0, 'graph_commits': 0, 'loc_query': 0}

# Repos excluded from the Lines-of-Code total. These are Unity projects whose committed
# Library/asset/.meta files inflate the count by millions of "lines". Their commits and
# the repo count are unaffected — only their LOC additions/deletions are skipped.
# Matched on the repository name alone, so transferring one into an organization (which
# changes nameWithOwner) cannot silently re-inflate the LOC total by millions again.
LOC_EXCLUDE_NAMES = {'GP1_GRP04', 'VampSurvEX', 'AI---Project-Kim', 'NPA'}


class AntiAbuseLimit(Exception):
    """Raised when GitHub answers 403 — the undocumented anti-abuse limit was hit"""


def loc_excluded(name_with_owner):
    """
    Returns True if this repo's additions/deletions should be left out of the LOC total
    e.g. 'GitJamieK/NPA' and 'SomeOrg/NPA' are both excluded
    """
    return name_with_owner.split('/')[-1] in LOC_EXCLUDE_NAMES


def daily_readme(birthday):
    """
    Returns the length of time since I was born
    e.g. 'XX years, XX months, XX days'
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years), 
        diff.months, 'month' + format_plural(diff.months), 
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')


def format_plural(unit):
    """
    Returns a properly formatted number
    e.g.
    'day' + format_plural(diff.days) == 5
    >>> '5 days'
    'day' + format_plural(diff.days) == 1
    >>> '1 day'
    """
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    Retries transient 5xx / rate-limit responses (GitHub's API 502s under load)
    with exponential backoff before giving up.
    """
    for attempt in range(5):
        request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
        if request.status_code == 200:
            return request
        if request.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(2 ** attempt)  # 1, 2, 4, 8 seconds
            continue
        raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def graph_commits(start_date, end_date):
    """
    Uses GitHub's GraphQL v4 API to return my total commit count
    """
    query_count('graph_commits')
    query = '''
    query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }'''
    variables = {'start_date': start_date,'end_date': end_date, 'login': USER_NAME}
    request = simple_request(graph_commits.__name__, query, variables)
    return int(request.json()['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions'])


def graph_repos_stars(count_type, owner_affiliation, cursor=None, add_loc=0, del_loc=0):
    """
    Uses GitHub's GraphQL v4 API to return my total repository, star, or lines of code count.
    """
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    if request.status_code == 200:
        if count_type == 'repos':
            return request.json()['data']['user']['repositories']['totalCount']
        elif count_type == 'stars':
            return stars_counter(request.json()['data']['user']['repositories']['edges'])


def recursive_loc(owner, repo_name, count_diffs=True):
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to walk a repository's default branch
    a page of commits at a time, and totals up the additions/deletions of the commits I authored.
    Returns (additions, deletions, my_commits), or None if GitHub never answered a page
    successfully — the caller then keeps the numbers already in the cache, so one unreachable
    repository can no longer fail the whole build.
    Asking for additions/deletions is what makes this query expensive enough for GitHub to time
    out (502 Bad Gateway), so it is skipped for repos whose LOC is excluded anyway, and the page
    size is halved on every retry.
    """
    diff_fields = 'deletions\n                                    additions' if count_diffs else ''
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String, $page_size: Int!) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: $page_size, after: $cursor) {
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    ''' + diff_fields + '''
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    addition_total, deletion_total, my_commits = 0, 0, 0
    cursor, page_size = None, 100
    while True:
        # I cannot use simple_request(), because a failure here must not abort the whole run.
        history = None
        for attempt in range(6):
            query_count('recursive_loc')
            variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor, 'page_size': page_size}
            request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
            if request.status_code == 200:
                repository = (request.json().get('data') or {}).get('repository')
                if repository is None or repository['defaultBranchRef'] is None:
                    # On the first page this means the repo is empty or unreadable by this token.
                    # Mid-pagination it means the repo changed under us — keep the cached numbers.
                    return (0, 0, 0) if cursor is None else None
                history = repository['defaultBranchRef']['target']['history']
                break
            if request.status_code == 403:
                raise AntiAbuseLimit('Too many requests in a short amount of time!\nYou\'ve hit the non-documented anti-abuse limit!')
            if request.status_code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(2 ** attempt)          # 1, 2, 4, 8, 16 seconds
                page_size = max(10, page_size // 2) # smaller pages are cheaper for GitHub to answer
                continue
            print('   ! recursive_loc() failed for', owner + '/' + repo_name, 'with a', request.status_code, '-', request.text[:120].replace('\n', ' '))
            return None

        for node in history['edges']:
            if node['node']['author']['user'] == OWNER_ID:
                my_commits += 1
                addition_total += node['node'].get('additions', 0)
                deletion_total += node['node'].get('deletions', 0)

        if not history['pageInfo']['hasNextPage']:
            return addition_total, deletion_total, my_commits
        cursor = history['pageInfo']['endCursor']


def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=[]):
    """
    Uses GitHub's GraphQL v4 API to query all the repositories I have access to (with respect to owner_affiliation)
    Queries 60 repos at a time, because larger queries give a 502 timeout error and smaller queries send too many
    requests and also give a 502 error.
    Returns the total number of lines of code in all repositories
    """
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
            edges {
                node {
                    ... on Repository {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    if request.json()['data']['user']['repositories']['pageInfo']['hasNextPage']:   # If repository data has another page
        edges += request.json()['data']['user']['repositories']['edges']            # Add on to the LoC count
        return loc_query(owner_affiliation, comment_size, force_cache, request.json()['data']['user']['repositories']['pageInfo']['endCursor'], edges)
    else:
        return cache_builder(edges + request.json()['data']['user']['repositories']['edges'], comment_size, force_cache)


def cache_filename():
    """
    Returns the path of the cache file, which is unique per user
    """
    return 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    """
    Checks each repository in edges to see if it has been updated since the last time it was cached
    If it has, run recursive_loc on that repository to update the LOC count

    Rows are looked up by the hash of nameWithOwner instead of by their position in the file, and
    the file is never wiped wholesale. Renaming a repo, transferring one into an organization,
    adding one or losing access to one therefore only costs a recalculation of that repo — it no
    longer invalidates every other row and forces a full (and 502-prone) rebuild of every total.
    """
    filename = cache_filename()
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError: # If the cache file doesn't exist, start from scratch
        lines = []
    cache_comment = lines[:comment_size] # save the comment block
    while len(cache_comment) < comment_size:
        cache_comment.append('This line is a comment block. Write whatever you want here.\n')

    cached_rows = {} # repo hash -> [hash, commit count, my commits, additions, deletions]
    if not force_cache:
        for line in lines[comment_size:]:
            row = line.split()
            if len(row) == 5: cached_rows[row[0]] = row

    cached = True # Assume all repositories are cached
    rows, unreachable, aborted = [], [], False
    for edge in edges:
        name_with_owner = edge['node']['nameWithOwner']
        repo_hash = hashlib.sha256(name_with_owner.encode('utf-8')).hexdigest()
        row = cached_rows.get(repo_hash, [repo_hash, '-1', '0', '0', '0']) # -1 == never counted yet
        if not aborted:
            try:
                commit_count = edge['node']['defaultBranchRef']['target']['history']['totalCount']
            except TypeError: # If the repo is empty
                commit_count = 0
            if commit_count == 0:
                row = [repo_hash, '0', '0', '0', '0']
            elif int(row[1]) != commit_count: # if commit count has changed, update loc for that repo
                cached = False
                owner, repo_name = name_with_owner.split('/')
                try:
                    loc = recursive_loc(owner, repo_name, count_diffs=not loc_excluded(name_with_owner))
                except AntiAbuseLimit as error: # stop querying, but save what was counted so far
                    print('   !', error)
                    loc, aborted = None, True
                if loc is None: # keep the cached numbers, so the next run picks this repo up again
                    unreachable.append(name_with_owner)
                else:
                    row = [repo_hash, str(commit_count), str(loc[2]), str(loc[0]), str(loc[1])]
        rows.append(row)

    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(' '.join(row) + '\n' for row in rows)

    for edge, row in zip(edges, rows):
        if loc_excluded(edge['node']['nameWithOwner']): continue  # skip asset-inflated repos' LOC
        loc_add += int(row[3])
        loc_del += int(row[4])
    if unreachable:
        print('   ! kept the cached numbers for', len(unreachable), 'repo(s) GitHub would not return:', ', '.join(unreachable))
    return [loc_add, loc_del, loc_add - loc_del, cached]


def stars_counter(data):
    """
    Count total stars in repositories owned by me
    """
    total_stars = 0
    for node in data: total_stars += node['node']['stargazers']['totalCount']
    return total_stars


def svg_overwrite(filename, age_data, commit_data, star_data, repo_data, contrib_data, follower_data, loc_data):
    """
    Parse SVG files and update elements with my age, commits, stars, repositories, and lines written
    """
    tree = etree.parse(filename)
    root = tree.getroot()
    justify_format(root, 'age_data', age_data, 42) # = R-11 in gen_svg.py; right-aligns the uptime value
    # Combined-line layout: "Repos {Contributed} | Stars" / "Commits | Followers".
    # Widths chosen so both "|" align, Stars/Followers end at the right edge, and the
    # LOC "(" sits under the "|". Must match STAT_LEN in assets/gen_svg.py.
    justify_format(root, 'repo_data', repo_data, 3)
    justify_format(root, 'contrib_data', contrib_data, 3)
    justify_format(root, 'star_data', star_data, 13)
    justify_format(root, 'commit_data', commit_data, 17)
    justify_format(root, 'follower_data', follower_data, 9)
    justify_format(root, 'loc_data', loc_data[2], 11)  # total -> "(" under the "|"
    justify_format(root, 'loc_add', loc_data[0], 8)
    justify_format(root, 'loc_del', loc_data[1], 6)    # deletions -> ")" at the far edge
    tree.write(filename, encoding='utf-8', xml_declaration=True)


def justify_format(root, element_id, new_text, length=0):
    """
    Updates and formats the text of the element, and modifes the amount of dots in the previous element to justify the new text on the svg
    """
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)
    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: '', 1: ' ', 2: '. '}
        dot_string = dot_map[just_len]
    else:
        dot_string = ' ' + ('.' * just_len) + ' '
    find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root, element_id, new_text):
    """
    Finds the element in the SVG file and replaces its text with a new value
    """
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def commit_counter(comment_size):
    """
    Counts up my total commits, using the cache file created by cache_builder.
    """
    total_commits = 0
    with open(cache_filename(), 'r') as f:
        data = f.readlines()
    cache_comment = data[:comment_size] # save the comment block
    data = data[comment_size:] # remove those lines
    for line in data:
        total_commits += int(line.split()[2])
    return total_commits


def user_getter(username):
    """
    Returns the account ID and creation time of the user
    """
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    variables = {'login': username}
    request = simple_request(user_getter.__name__, query, variables)
    return {'id': request.json()['data']['user']['id']}, request.json()['data']['user']['createdAt']

def follower_getter(username):
    """
    Returns the number of followers of the user
    """
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def query_count(funct_id):
    """
    Counts how many times the GitHub GraphQL API is called
    """
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1


def perf_counter(funct, *args):
    """
    Calculates the time it takes for a function to run
    Returns the function result and the time differential
    """
    start = time.perf_counter()
    funct_return = funct(*args)
    return funct_return, time.perf_counter() - start


def formatter(query_type, difference, funct_return=False, whitespace=0):
    """
    Prints a formatted time differential
    Returns formatted result if whitespace is specified, otherwise returns raw result
    """
    print('{:<23}'.format('   ' + query_type + ':'), sep='', end='')
    print('{:>12}'.format('%.4f' % difference + ' s ')) if difference > 1 else print('{:>12}'.format('%.4f' % (difference * 1000) + ' ms'))
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"
    return funct_return


if __name__ == '__main__':
    """
    Jamie Kofler (GitJamieK) — GitHub profile stats generator
    """
    print('Calculation times:')
    # define global variable for owner ID and calculate user's creation date
    # e.g {'id': 'MDQ6VXNlc...'} and 2019-11-03T21:15:07Z for the given username
    user_data, user_time = perf_counter(user_getter, USER_NAME)
    OWNER_ID, acc_date = user_data
    formatter('account data', user_time)
    age_data, age_time = perf_counter(daily_readme, datetime.datetime(2001, 11, 20))
    formatter('age calculation', age_time)
    total_loc, loc_time = perf_counter(loc_query, ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'], 7)
    formatter('LOC (cached)', loc_time) if total_loc[-1] else formatter('LOC (no cache)', loc_time)
    commit_data, commit_time = perf_counter(commit_counter, 7)
    star_data, star_time = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
    # "Repos" counts what I actually own — my own account plus my organizations — so transferring
    # a repo into one of them does not drop it from the count. Repos I am only a collaborator on
    # stay out of this number and show up in the {Contributed} one instead.
    repo_data, repo_time = perf_counter(graph_repos_stars, 'repos', ['OWNER', 'ORGANIZATION_MEMBER'])
    contrib_data, contrib_time = perf_counter(graph_repos_stars, 'repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)

    for index in range(len(total_loc)-1): total_loc[index] = '{:,}'.format(total_loc[index]) # format added, deleted, and total LOC

    svg_overwrite('dark_mode.svg', age_data, commit_data, star_data, repo_data, contrib_data, follower_data, total_loc[:-1])
    svg_overwrite('light_mode.svg', age_data, commit_data, star_data, repo_data, contrib_data, follower_data, total_loc[:-1])

    # move cursor to override 'Calculation times:' with 'Total function time:' and the total function time, then move cursor back
    print('\033[F\033[F\033[F\033[F\033[F\033[F\033[F\033[F',
        '{:<21}'.format('Total function time:'), '{:>11}'.format('%.4f' % (user_time + age_time + loc_time + commit_time + star_time + repo_time + contrib_time)),
        ' s \033[E\033[E\033[E\033[E\033[E\033[E\033[E\033[E', sep='')

    print('Total GitHub GraphQL API calls:', '{:>3}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items(): print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))