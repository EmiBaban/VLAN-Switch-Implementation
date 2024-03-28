#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

mac_table = {}

def add_vlan_tag(data, vlan_tag):
    return data[0:12] + vlan_tag + data[12:]

def delete_vlan_tag(data):
    return data[0:12] + data[16:]

def read_config_file(switch_id):
    file = f"./configs/switch{switch_id}.cfg"
    switch_interfaces = []

    try:
        with open(file, 'r') as f:
            lines = f.readlines()

            for line in lines:
                parts = line.strip().split()

                if len(parts) >= 2:
                    switch_interfaces.append(MyInterface(parts[1], parts[0]))

    except FileNotFoundError:
        print(f"File {file} not found.")
    except Exception as e:
        print(f"Error reading config file: {e}")
    return switch_interfaces

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec():
    while True:
        time.sleep(1)


def findInterface(name, switch_interfaces):
    for x in switch_interfaces:
        if x.name == name:
            return x

class MyInterface:
    def __init__(self, vlan_id, name):
        self.vlan_id = str(vlan_id)
        self.name = str(name)

    def __str__(self):
        return f"Interface {self.name}, VLAN {self.vlan_id}"

def is_unicast(address):
    return (int(address[0], 16) & 1) == 0

def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_r               et value + 1
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    switch_interfaces = read_config_file(switch_id)

    print("# Starting switch with id {}".format(switch_id), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()

    # Printing interface names
    for i in interfaces:
        print(get_interface_name(i))

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        # Print the MAC src and MAC dst in human-readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')

        print("Received frame of size {} on interface {}".format(length, interface), flush=True)

        mac_table[src_mac] = interface        


        if dest_mac in mac_table:
            send_to_link(mac_table[dest_mac], data, length)
        else:
            if vlan_id == -1:
                sw_int = findInterface(get_interface_name(interface), switch_interfaces)
                vlan_id = sw_int.vlan_id       
                vlan_tag = create_vlan_tag(int(vlan_id))

                for i in interfaces:
                    if i != interface:
                        sw_int_dest = findInterface(get_interface_name(i), switch_interfaces)
                        if sw_int_dest is not None:
                            if sw_int_dest.vlan_id == 'T':
                                send_to_link(i, bytes(add_vlan_tag(data, vlan_tag)), length + 4)
                            elif int(sw_int_dest.vlan_id) == vlan_id and sw_int_dest.vlan_id != 'T':
                                send_to_link(i, data, length)
            else:
                for i in interfaces:
                    if i != interface:
                        sw_int_dest = findInterface(get_interface_name(i), switch_interfaces)
                        if sw_int_dest is not None:
                            if sw_int_dest.vlan_id == 'T':
                                send_to_link(i, data, length)
                            elif int(sw_int_dest.vlan_id) == vlan_id and sw_int_dest.vlan_id != 'T':
                                send_to_link(i, bytes(delete_vlan_tag(data)), length - 4)


if __name__ == "__main__":
    main()
