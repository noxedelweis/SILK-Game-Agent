"""Explicit split between stable operations and opt-in experimental features."""
STABLE_ACTIONS = frozenset({'status', 'update', 'search', 'ask', 'replay', 'observer',
                            'rollback', 'tests', 'folder', 'step', 'launch', 'session',
                            'session-watch', 'nav', 'nav2', 'probe-install', 'environment'})
EXPERIMENTAL_ACTIONS = frozenset({'object-preview', 'object-nav'})


def feature_channel(action):
    if action in STABLE_ACTIONS:
        return 'stable'
    if action in EXPERIMENTAL_ACTIONS:
        return 'experimental'
    raise ValueError('Unknown SILK feature: ' + str(action))
