---
title: "Applied Energistics 2 Guide - Getting Started"
source_url: "https://guide.appliedenergistics.org/1.21.1/getting-started"
minecraft_version: "1.21.1"
mod: "Applied Energistics 2"
source_type: "official_guide"
fetched_at: "2026-09-13T22:56:14+08:00"
---
The following information only applies to Applied Energistics 2 in Minecraft 1.20 and newer.

# Getting Started

## Getting The Initial Materials)

To get started with Applied Energistics 2, one must first find a [meteorite](/1.21.1/ae2-mechanics/meteorites). These are fairly common and tend to leave massive holes in the terrain, so you've probably encountered one in your travels.
If you haven't, you can craft a Meteorite Compass, which will point toward the nearest Mysterious Cube.

Once you have found a meteorite, mine into its center. You will find certus quartz clusters, certus quartz buds, [budding certus blocks](/1.21.1/items-blocks-machines/budding_certus) of various types, and a Mysterious Cube in the center.

Mine the certus quartz clusters and any certus quartz blocks you find. You can also pick up the budding certus blocks, but without silk touch they will degrade by 1 tier.

Do not break any flawless budding certus, as even with silk touch they will degrade to flawed budding certus, and it is impossible to repair them back to flawless.

Also mine the Mysterious Cube in the center of the meteorite to gain all 4 inscriber presses.

## Growing Certus Quartz

Certus quartz buds will sprout from [budding certus blocks](/1.21.1/items-blocks-machines/budding_certus), similar to amethyst. If you break a bud that is not finished
growing, it will drop one Certus Quartz Dust, unchanged by fortune. If you break a fully grown cluster, it will drop four
Certus Quartz Crystals, and fortune will increase this number.

There are 4 tiers of budding certus blocks: Flawless, Flawed, Chipped, and Damaged.

Every time a bud grows by another stage, the budding block has a chance to degrade by one tier, eventually turning into
a plain certus quartz block. They can be repaired (and new budding blocks created) by throwing the budding block (or a
certus quartz block) in water with one or more Charged Certus Quartz Crystal.

![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!fluids/minecraft/water.kDjMj2MjIGJq.webp) Throw in Water![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!items/ae2/charged_certus_quartz_crystal.Ud0RCmXSmRPE.webp)![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!items/ae2/quartz_block.I1uyXS3wJKk2.png)![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!items/ae2/damaged_budding_quartz.kW8rwBPX9Dw6.png)

Flawless budding certus blocks will not degrade and will generate certus infinitely. However they cannot be crafted or moved
with a pickaxe, even with silk touch. (they *can* be moved with [spatial storage](/1.21.1/ae2-mechanics/spatial-io) though)

By themselves, certus quartz buds grow very slowly. Luckily the Growth Accelerator massively
accelerates this process when placed adjacent to the budding block. You should build a few of these as your first priority.

If you don't have enough quartz to also make an Energy Acceptor or Vibration Chamber,
you can make a Wooden Crank and stick it on the end of your accelerator.

Harvesting the certus automatically is [described here](/1.21.1/example-setups/simple-certus-farm).

## A Quick Aside on Fluix

Another material you will need is Fluix, which you have already encountered in making growth accelerators. It is made by throwing charged certus, redstone, and nether quartz in water. Doing this automatically is "left as an exercise for the reader."

The Charger is required to produce Charged Certus Quartz Crystal., if you haven't made one already.

## Inscribing Some Processors

In your looting of a meteorite, you will have found four "presses" from breaking the Mysterious Cube. These are used in the Inscriber to make the three types of processor.

![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!items/ae2/silicon_press.Xk7PErvUeJrc.png)![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!items/ae2/logic_processor_press.LZgS29WI2u7b.png)![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!items/ae2/calculation_processor_press.pG1X9YCpd2PQ.png)![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/!items/ae2/engineering_processor_press.3Yuzw8yhzNV6.png)

The inscriber is a sided machine, much like the vanilla furnace. Inserting from the top or bottom places items in the top or bottom slots, and inserting from the side or back inserts into the center slot. Results can be pulled from the side or back.

To facilitate automation with hoppers (and possibly reduce pipe spaghetti), inscribers can be rotated with a Certus Quartz Wrench.

Produce a few of each type of processor in preparation for the next step, making a very basic ME system. Automating processor production is "[left as an exercise for the reader](/1.21.1/example-setups/processor-automation)".

## Matter Energy Tech: ME Networks and Storage

### What is ME Storage?

Its pronounced Emm-Eee, and stands for Matter Energy.

Matter Energy is the main component of Applied Energistics 2, it's like a mad scientist version of a Multi-Block chest,
and it can revolutionize your storage situation. ME is extremely different than other storage systems in Minecraft, and
it might take a little out of the box thinking to get used to; but once you get started vast amounts of storage in tiny
space, and multiple access terminals are just the tip of the iceberg of what becomes possible.

### What do I need to know to get started?

First, ME Stores items inside of other items, called [Storage cells](/1.21.1/items-blocks-machines/storage_cells); there are 5 tiers with ever increasing amounts of
storage. In order to use a Storage Cell it must be placed inside either an ME Chest,
or an ME Drive.

The ME Chest shows you the contents of the Cell as soon as its placed inside, and you
can add and remove items from it as if it were a Chest, with the exception that the items are
actually stored in the Storage cells, and not the ME Chest itself.

The ME Chest is quite situational and limited in utility. To really
take advantage of AE2, you need to set up an [ME Network](/1.21.1/ae2-mechanics/me-network-connections).

## Your Very First ME System

Now that you have all of the basic materials and machines for Applied Energistics 2, you can make your first ME (Matter Energy) system. This will be a very basic one, no autocrafting, no logistics, just nice, simple, searchable storage.

- Your ingredients list:

1x ME Drive
1x ME Terminal or ME Crafting Terminal
1x Energy Acceptor
A few [cables](/1.21.1/items-blocks-machines/cables), either glass, covered, or smart, but not dense
A few [storage cells](/1.21.1/items-blocks-machines/storage_cells), recommended of the 4k variety for a good mix of
capacity and types (it would be more efficient to [partition](/1.21.1/items-blocks-machines/cell_workbench) a mix of 4k and 1k but that's a complexity we won't go into now)
    - 1x ME Drive
    - 1x ME Terminal or ME Crafting Terminal
    - 1x Energy Acceptor
    - A few [cables](/1.21.1/items-blocks-machines/cables), either glass, covered, or smart, but not dense
    - A few [storage cells](/1.21.1/items-blocks-machines/storage_cells), recommended of the 4k variety for a good mix of
capacity and types (it would be more efficient to [partition](/1.21.1/items-blocks-machines/cell_workbench) a mix of 4k and 1k but that's a complexity we won't go into now)

---

1. Place the drive down.
2. The energy acceptor (and several other AE2 [devices](/1.21.1/ae2-mechanics/devices)) comes in 2 modes, cube and flat. They can be switched between in a crafting grid. If your energy acceptor is a cube, place it down next to the drive. If it's a flat square, place a cable on the drive and place the acceptor on that.
3. Run energy into the energy acceptor with a cable/pipe/conduit from your favorite energy-generation mod.
4. Place a cable on top of the drive (or otherwise at eye level) and place your terminal or crafting terminal on it.
5. Put your storage cells into the drive
6. Profit
7. Fiddle with the terminal's settings
8. Bask in your ultimate power and ability
9. Realize that this network is, in the grand scheme, rather small

### Expanding your Network

So you have some basic storage, and access to that storage, it's a good start, but you'll likely be looking to maybe
automate some processing.

A great example of this is to place a ME Export Bus on the top of a furnace to
dump in ores, and a ME Import Bus
on the bottom of the furnace to extract furnaced ores.

The ME Export Bus lets you export items from the network, into the attached
inventory, while the ME Import Bus imports items from the attached inventory into
the network.

### Overcoming Limits

At this point you probably getting close to 8 or so [devices](/1.21.1/ae2-mechanics/devices), once you hit 9 devices you'll have to start
managing [channels](/1.21.1/ae2-mechanics/channels). Many devices but not all, require a channel to
function.

By default a network can support 8 channels, once you break this limit, you'll have to add
an ME Controller to your network. this allows you to expand your network greatly.
[Smart cables](/1.21.1/items-blocks-machines/cables) will allow you to see how channels are routed through your network. Use them extensively when starting out to learn how channels act, or if you have a lot of redstone and glowstone.
