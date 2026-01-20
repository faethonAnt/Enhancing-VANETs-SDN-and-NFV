#!/usr/bin/env python3

from mininet.log import setLogLevel, info
from mininet.node import RemoteController
from mn_wifi.cli import CLI
from mn_wifi.net import Mininet_wifi
from mn_wifi.node import OVSKernelAP
from mn_wifi.link import wmediumd
from mn_wifi.wmediumdConnector import interference
from mn_wifi.sumo.runner import sumo
import time


MIN_X, MIN_Y, MAX_X, MAX_Y = -100.0, -400.0, 500.0, 200.0
PAD = 20.0

SUMO_CFG = "/home/wifi/mininet-wifi/mn_wifi/sumo/data/girogiro.sumocfg"


def topology():
    # Use RemoteController talk to POX
    net = Mininet_wifi(controller=RemoteController,
                       accessPoint=OVSKernelAP,
                       link=wmediumd, wmediumd_mode=interference)

    net.setPropagationModel(model="logDistance", exp=3.4, sL=2)

    info("*** Creating 25 vehicles (cars)\n")
    cars = []
    for i in range(7):
        c = net.addCar(f'car{i+1}', wlans=1,
                       ip=f'10.0.0.{i+1}/24',
                       position='0,0,0', range=60)
        cars.append(c)

    info("*** Creating 6 RSUs in a 3x2 grid\n")
    rsu1 = net.addAccessPoint('rsu1', ssid='vanet', mode='g', channel='1',
                              position='0,100,0', range=170,
                              failMode='standalone')
    rsu2 = net.addAccessPoint('rsu2', ssid='vanet', mode='g', channel='1',
                              position='200,100,0', range=170,
                              failMode='standalone')
    rsu3 = net.addAccessPoint('rsu3', ssid='vanet', mode='g', channel='1',
                              position='400,100,0', range=170,
                              failMode='standalone')
    rsu4 = net.addAccessPoint('rsu4', ssid='vanet', mode='g', channel='1',
                              position='0,-300,0', range=170,
                              failMode='standalone')
    rsu5 = net.addAccessPoint('rsu5', ssid='vanet', mode='g', channel='1',
                              position='200,-300,0', range=170,
                              failMode='standalone')
    rsu6 = net.addAccessPoint('rsu6', ssid='vanet', mode='g', channel='1',
                              position='400,-300,0', range=170,
                              failMode='standalone')

    aps = [rsu1, rsu2, rsu3, rsu4, rsu5, rsu6]

    info("*** Creating backhaul (SDN switches + server)\n")
    srv = net.addHost('srv', ip='10.0.0.254/24')

    # Give fixed DPIDs so POX can identify each switch
    # s1 = core, s2 = agg1 (west), s3 = agg2 (east)
    core = net.addSwitch('s1', dpid='0000000000000001', failMode='secure')
    agg1 = net.addSwitch('s2', dpid='0000000000000002', failMode='secure')
    agg2 = net.addSwitch('s3', dpid='0000000000000003', failMode='secure')

    info("*** Linking RSUs to aggregation switches\n")
    # West+mid to agg1
    net.addLink(rsu1, agg1, bw=20, delay='5ms', use_htb=True)
    net.addLink(rsu2, agg1, bw=20, delay='5ms', use_htb=True)
    net.addLink(rsu4, agg1, bw=20, delay='5ms', use_htb=True)
    net.addLink(rsu5, agg1, bw=20, delay='5ms', use_htb=True)

    # East to agg2
    net.addLink(rsu3, agg2, bw=20, delay='5ms', use_htb=True)
    net.addLink(rsu6, agg2, bw=20, delay='5ms', use_htb=True)

    info("*** Adding bottleneck link agg1 <-> agg2 (same as baseline)\n")
    net.addLink(agg1, agg2,
                bw=5, delay='50ms', loss=2,
                max_queue_size=50, use_htb=True)

    info("*** Adding good links to core\n")
    # agg2 -> core
    net.addLink(agg2, core, bw=50, delay='2ms', use_htb=True)
    # NEW SDN PATH: agg1 -> core (bypasses bottleneck)
    net.addLink(agg1, core, bw=50, delay='2ms', use_htb=True)
    # core -> srv
    net.addLink(core, srv, bw=50, delay='2ms', use_htb=True)

    info("*** Configuring wifi nodes\n")
    net.configureWifiNodes()

    info(f"*** SUMO config: {SUMO_CFG}\n")
    net.useExternalProgram(
        program=sumo,
        config_file=SUMO_CFG,
        port=8813,
        extra_params=["--start", "--delay", "200", "--step-length", "0.1"],
        clients=1,
        exec_order=0
    )

    info("*** Starting network with RemoteController\n")
    c0 = net.addController('c0', controller=RemoteController,
                           ip='127.0.0.1', port=6633)
    net.build()

    # Start APs and SDN switches (all pointing to c0)
    for ap in aps:
        ap.start([c0])
    agg1.start([c0])
    agg2.start([c0])
    core.start([c0])


    info("*** Configuring AP bridges with NORMAL\n")
    for ap in aps:
        ap.cmd(f'ovs-vsctl -- if-exists del-port {ap.name} {ap.name}-wlan2')
        ap.cmd(f'ovs-vsctl --may-exist add-port {ap.name} {ap.name}-wlan1')
        info(ap.cmd(f'ovs-vsctl list-ports {ap.name}'))

        ap.cmd(
            f'ovs-ofctl -O OpenFlow13 add-flow {ap.name} "actions=NORMAL" || '
            f'ovs-ofctl -O OpenFlow10 add-flow {ap.name} "actions=NORMAL"'
        )


    time.sleep(2.0)

    info("*** Enabling telemetry\n")
    nodes = cars + aps
    net.telemetry(nodes=nodes, data_type='position',
                  min_x=MIN_X - PAD, min_y=MIN_Y - PAD,
                  max_x=MAX_X + PAD, max_y=MAX_Y + PAD)

    net.plotGraph(max_x=MAX_X + PAD, max_y=MAX_Y + PAD)

    info("*** Starting CLI (SDN mode)\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')