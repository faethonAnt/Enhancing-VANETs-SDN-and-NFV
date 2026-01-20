from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import IPAddr

log = core.getLogger()

SERVER_IP = IPAddr("10.0.0.254")

SWITCH_PORTS = {
    1: {  # core
        "to_agg2": 1,
        "to_agg1": 2,
        "to_srv": 3,
    },
    2: {  # agg1
        "rsu_ports": [1, 2, 3, 4],
        "to_agg2": 5,
        "to_core": 6,  # GOOD path to core
    },
    3: {  # agg2
        "rsu_ports": [1, 2],
        "to_agg1": 3,
        "to_core": 4,
    },
}


def add_flow(conn, priority, match, actions):
    """
    Helper to send a flow_mod with given match & actions.
    """
    fm = of.ofp_flow_mod()
    fm.priority = priority
    fm.match = match
    for a in actions:
        fm.actions.append(a)
    conn.send(fm)


def install_flows_core(conn):
    """
    Install flows on s1 (core).
    """
    ports = SWITCH_PORTS[1]
    p_agg2 = ports["to_agg2"]
    p_srv = ports["to_srv"]
    p_agg1 = ports["to_agg1"]

    log.info("Installing flows on core (s1)")

    # IP traffic TO the server: send to srv port
    m = of.ofp_match()
    m.dl_type = 0x0800  # IPv4
    m.nw_dst = SERVER_IP
    add_flow(conn, priority=100,
             match=m,
             actions=[of.ofp_action_output(port=p_srv)])

    # IP traffic FROM the server: send to both aggregation switches
    m = of.ofp_match()
    m.dl_type = 0x0800
    m.nw_src = SERVER_IP
    add_flow(conn, priority=100,
             match=m,
             actions=[of.ofp_action_output(port=p_agg1),
                      of.ofp_action_output(port=p_agg2)])

    # ARP: flood out all ports (low priority)
    m = of.ofp_match()
    m.dl_type = 0x0806  # ARP
    add_flow(conn, priority=10,
             match=m,
             actions=[of.ofp_action_output(port=of.OFPP_FLOOD)])

    # Default: flood (very low priority)
    m = of.ofp_match()  # match everything
    add_flow(conn, priority=1,
             match=m,
             actions=[of.ofp_action_output(port=of.OFPP_FLOOD)])


def install_flows_agg1(conn):
    """
    Install flows on s2 (agg1 - west).
    """
    ports = SWITCH_PORTS[2]
    rsu_ports = ports["rsu_ports"]
    p_core = ports["to_core"]
    # p_agg2 = ports["to_agg2"]  # we DELIBERATELY avoid using the bottleneck for server traffic

    log.info("Installing flows on agg1 (s2)")

    # IP traffic TO the server: go directly to core via GOOD link (avoid bottleneck).
    m = of.ofp_match()
    m.dl_type = 0x0800
    m.nw_dst = SERVER_IP
    add_flow(conn, priority=100,
             match=m,
             actions=[of.ofp_action_output(port=p_core)])

    # IP traffic FROM the server: send to all RSU-facing ports
    m = of.ofp_match()
    m.dl_type = 0x0800
    m.nw_src = SERVER_IP
    actions = [of.ofp_action_output(port=p) for p in rsu_ports]
    add_flow(conn, priority=100, match=m, actions=actions)

    # ARP: flood
    m = of.ofp_match()
    m.dl_type = 0x0806
    add_flow(conn, priority=10,
             match=m,
             actions=[of.ofp_action_output(port=of.OFPP_FLOOD)])

    # Default flood
    m = of.ofp_match()
    add_flow(conn, priority=1,
             match=m,
             actions=[of.ofp_action_output(port=of.OFPP_FLOOD)])


def install_flows_agg2(conn):
    """
    Install flows on s3 (agg2 - east).
    """
    ports = SWITCH_PORTS[3]
    rsu_ports = ports["rsu_ports"]
    p_core = ports["to_core"]

    log.info("Installing flows on agg2 (s3)")

    # IP traffic TO the server: go to core
    m = of.ofp_match()
    m.dl_type = 0x0800
    m.nw_dst = SERVER_IP
    add_flow(conn, priority=100,
             match=m,
             actions=[of.ofp_action_output(port=p_core)])

    # IP traffic FROM the server: to all RSUs on this side
    m = of.ofp_match()
    m.dl_type = 0x0800
    m.nw_src = SERVER_IP
    actions = [of.ofp_action_output(port=p) for p in rsu_ports]
    add_flow(conn, priority=100, match=m, actions=actions)

    # ARP: flood
    m = of.ofp_match()
    m.dl_type = 0x0806
    add_flow(conn, priority=10,
             match=m,
             actions=[of.ofp_action_output(port=of.OFPP_FLOOD)])

    # Default flood
    m = of.ofp_match()
    add_flow(conn, priority=1,
             match=m,
             actions=[of.ofp_action_output(port=of.OFPP_FLOOD)])


def _handle_ConnectionUp(event):
    dpid = event.dpid
    conn = event.connection
    log.info("Switch %s has connected (dpid=%s)", dpid, hex(dpid))

    if dpid == 1:
        install_flows_core(conn)
    elif dpid == 2:
        install_flows_agg1(conn)
    elif dpid == 3:
        install_flows_agg2(conn)
    else:

        log.warn("Unknown switch dpid=%s, installing simple flood rule", dpid)
        m = of.ofp_match()
        add_flow(conn, priority=1,
                 match=m,
                 actions=[of.ofp_action_output(port=of.OFPP_FLOOD)])


def launch():
    log.info("Launching VANET SDN controller (static flows for server path)")
    core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
