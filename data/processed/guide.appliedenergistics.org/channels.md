---
title: "Applied Energistics 2 Guide - Channels"
source_url: "https://guide.appliedenergistics.org/1.21.1/ae2-mechanics/channels"
minecraft_version: "1.21.1"
mod: "Applied Energistics 2"
source_type: "official_guide"
fetched_at: "2026-08-26T01:33:08+08:00"
---
[![](/_next/static/media/logo_00.eb0ce7a0.png)Applied Energistics 2](/)

ChannelsApplied Energistics 2's [ME Networks](/1.21.1/ae2-mechanics/me-network-connections) require
Channels to support [devices](/1.21.1/ae2-mechanics/devices) which use networked storage, or other network
services. Think of channels like USB cables to all your devices. A computer only has so many USB ports and can only support
so many devices connected to it. Most machines, full-block devices, and standard cables can only pass through
up to 8 channels. You can think of full-block devices and standard cables as a bundle of 8 "channel wires". However, [dense cables](/1.21.1/items-blocks-machines/cables#dense-cable) can support up
to 32 channels. The only other devices capable of transmitting 32 are ME P2P Tunnel
and the [Quantum Network Bridge](/1.21.1/items-blocks-machines/quantum_bridge). Each time a device uses up a channel, imagine pulling off a usb "wire" from
the bundle, which obviously means that "wire" isn't available further down the line.$!![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/ae2/ae2-mechanics/channels_scene1.mNkgwoCrP5cI.png)/$An easy way to see how channels are being used and routed through your network is to use [smart cables](/1.21.1/items-blocks-machines/cables), which will display on them the paths and usage of channels.Channels will consume 1⁄128 ae/t per node they transverse, this means that by
adding a ME Controller for a
network with 8 devices and over 96 nodes your power usage might actually
decrease power consumption because it changes how channels are allocated.Of note, **CHANNELS HAVE NOTHING TO DO WITH CABLE COLOR**, all cable color does is make cables not connect.Channel RoutingWhen using a ME Controller,
channels route via 3 steps. They first take the shortest path through adjacent machines to the nearest [normal cable](/1.21.1/items-blocks-machines/cables)
(glass, covered, or smart). They then take the shortest path through that normal cable to the nearest [dense cable](/1.21.1/items-blocks-machines/cables)
(dense or dense smart). They then take the shortest path through that dense cable to the ME Controller.
If the shortest path is already maxed out, some [devices](/1.21.1/ae2-mechanics/devices) may not get their required channels, use
colored cables, cable anchors and tunnels to your advantage to make sure your channels go in the path you desire.For example, in this case some drives don't get channels because although there is enough capacity in the cables, the
channels try to take the shortest path, overloading some cables while leaving others empty.$!![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/ae2/ae2-mechanics/channels_scene2.xmBNYtbtFC5o.png)/$This can be fixed by more carefully constraining the paths channels can take. Networks should be treelike (or bushlike).
Loops and ambiguous channel paths should be minimized.$!![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/ae2/ae2-mechanics/channels_scene3.hyZRWmmwNbRL.png)/$Ad-Hoc NetworksA Network without a ME Controller
is considered to be Ad-Hoc, and can support up to 8 channel using devices.
Once you exceed 8 devices the network's channel using devices will shutdown,
you can either remove devices, or add a ME Controller.Unlike with controllered networks, [smart cables](/1.21.1/items-blocks-machines/cables) on ad-hoc networks will show the number
of channels in use network-wide instead of the number of channels flowing through that specific cable.While using ad-hoc networks each device will
use 1 channel network wide, this is very different from how ME Controller allocate channels based on
shortest route.DesignAs mentioned before in [channel routing](/1.21.1/ae2-mechanics/channels#channel-routing), it's best to design your network in a treelike structure, with dense cables branching out from the controller, regular cables
branching out from the dense, and [devices](/1.21.1/ae2-mechanics/devices) in clusters of 8 or fewer on the regular cables.Here is an example of what not to do:Following the channel paths,
 Immediately exiting the controller to the right, we're bottlenecked to 8 channels because the drive acts like a normal cable.
However since we're not using a smart cable here we cannot see how many channels are in use. 8 channels left.
 The drive takes a channel.
7 channels left.
 2 channels go up to the terminals.
5 channels left.
 Continuing right, the interface takes another channel.
4 channels left.
 1 channel goes up to the pattern provider.
3 channels left.
 Continuing right, 1 channel goes up to the import bus.
2 channels left.
 The cluster of pattern providers feeding assemblers only gets 2 channels, so 2 of the providers do not get channels.Ultimately the error is in bottlenecking the channels and not thinking through how channels will be distributed.$!![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/ae2/ae2-mechanics/channels_scene4.aqpxmUjQsYQO.png)/$Here is an example of a good structure:$!![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/ae2/ae2-mechanics/channels_scene5.RmHsWMRnuD61.png)/$Channel ModesAE2 10.0.0 for Minecraft 1.18 introduces new options to change how AE2 channels behave in your world.
There's a new configuration option in the general section (`channels`) which controls this option, and a new in-game
command for operators to change the mode and the config from inside the game. The command is `/ae2 channelmode <mode>`
to change it and `/ae2 channelmode` to show the current mode. When the mode is changed in-game, all existing grids will
reboot and use the new mode immediately.This resurrects and improves upon the option that was available in Minecraft 1.12 and introduces better options for
players that just want a little more laid back gameplay but don't want the mechanic to be removed entirely.The following table lists the available modes in both the configuration file and command.SettingDescription`default`The standard mode with the channel capacities of cable and ad-hoc networks as described throughout this website`x2`All channel capacities are doubled (16 on normal cable, 64 on dense cable, ad-hoc networks support 16 channels)`x3`All channel capacities are tripled (24 on normal cable, 92 on dense cable, ad-hoc networks support 24 channels)`x4`All channel capacities are quadrupled (32 on normal cable, 128 on dense cable, ad-hoc networks support 32 channels)`infinite`All channel restrictions are removed. Controllers still reduce the power consumption of grids *significantly*. Smart cables will only toggle between completely off (no channels carried) and completely on (1 or more channels carried).

Minecraft  1.21.1  [[change](/)]
