# STUB — waiting for M1/M2/M3
class ResidualRiskReporter:
    def generate_notice(self, report):
        return "╔══════════════════════════════════════════════════════╗\n║ RESIDUAL RISK NOTICE                                ║\n╠══════════════════════════════════════════════════════╣\n║ Verdict: %-42s ║\n║ The requested memory was removed from this agent.    ║\n║ Residual risk: external copies cannot be guaranteed. ║\n╚══════════════════════════════════════════════════════╝" % report.verdict
