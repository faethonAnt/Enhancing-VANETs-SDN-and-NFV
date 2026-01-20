from pox.core import core
import pox.openflow.libopenflow_01 as of

log = core.getLogger()

# Χαρτογράφηση ports
PORTS = {
    "0000000000000001": {  # s1 core
        "agg2": 1,
        "agg1": 2,
        "srv":  3,
    },
    "0000000000000002": {  # s2 agg1
        "rsu1": 1,
        "rsu2": 2,
        "rsu4": 3,
        "rsu5": 4,
        "agg2": 5,   # bottleneck - ΔΕΝ θα το χρησιμοποιήσουμε
        "core": 6,
    },
    "0000000000000003": {  # s3 agg2
        "rsu3": 1,
        "rsu6": 2,
        "agg1": 3,   # bottleneck - ΔΕΝ θα το χρησιμοποιήσουμε
        "core": 4,
    },
}


def add_flow_single(conn, in_port, out_port):
    msg = of.ofp_flow_mod()
    msg.match.in_port = in_port
    msg.actions.append(of.ofp_action_output(port=out_port))
    conn.send(msg)


def add_flow_multi(conn, in_port, out_ports):
    msg = of.ofp_flow_mod()
    msg.match.in_port = in_port
    for p in out_ports:
        msg.actions.append(of.ofp_action_output(port=p))
    conn.send(msg)


def _handle_ConnectionUp(event):
    dpid_str = "%016x" % event.dpid
    conn = event.connection
    log.info("Switch %s connected, config proactive flows", dpid_str)

    # s1: core
    if dpid_str == "0000000000000001":
        p = PORTS[dpid_str]
        # agg1 -> srv
        add_flow_single(conn, p["agg1"], p["srv"])
        # agg2 -> srv
        add_flow_single(conn, p["agg2"], p["srv"])
        # srv -> agg1 + agg2 (broadcast προς τα aggregation)
        add_flow_multi(conn, p["srv"], [p["agg1"], p["agg2"]])

    # s2: agg1
    elif dpid_str == "0000000000000002":
        p = PORTS[dpid_str]
        rsu_ports = [p["rsu1"], p["rsu2"], p["rsu4"], p["rsu5"]]

        # Από όλα τα RSUs προς core
        for rp in rsu_ports:
            add_flow_single(conn, rp, p["core"])

        # Από core προς όλα τα RSUs
        add_flow_multi(conn, p["core"], rsu_ports)

    # s3: agg2
    elif dpid_str == "0000000000000003":
        p = PORTS[dpid_str]
        rsu_ports = [p["rsu3"], p["rsu6"]]

        # Από RSUs προς core
        for rp in rsu_ports:
            add_flow_single(conn, rp, p["core"])

        # Από core προς RSUs
        add_flow_multi(conn, p["core"], rsu_ports)


def launch():
    core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
    log.info("sdn_routing (proactive) module loaded")
