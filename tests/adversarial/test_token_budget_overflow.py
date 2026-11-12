from tests.claims._helpers import claim

def run(context): return claim("budget", {**context,"token_budget":10})

