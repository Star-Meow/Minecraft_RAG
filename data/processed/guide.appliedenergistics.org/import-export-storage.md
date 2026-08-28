---
title: "Applied Energistics 2 Guide - Import Export Storage"
source_url: "https://guide.appliedenergistics.org/1.21.1/ae2-mechanics/import-export-storage"
minecraft_version: "1.21.1"
mod: "Applied Energistics 2"
source_type: "official_guide"
fetched_at: "2026-08-26T01:33:07+08:00"
---
[![](/_next/static/media/logo_00.eb0ce7a0.png)Applied Energistics 2](/)

Import, Export, and Storage**your ME system and the world**An important concept in AE2 is the idea of Network Storage. It is the place in which the contents of a network are stored,
usually [storage cells](/1.21.1/items-blocks-machines/storage_cells) or whatever inventory a ME Storage Bus
is connected to. Most AE2 [devices](/1.21.1/ae2-mechanics/devices) interact with it in one way or another.For example,
ME Import Busses push things into network storage
ME Export Busses pull things from network storage
ME Interfaces both pull from and push to network storage
[Terminals](/1.21.1/items-blocks-machines/terminals) both push to and pull from network storage when you insert or take items, or to refill the crafting slots
ME Storage Busses don't really push to or pull from storage, they push to or pull from the connected inventory
in order to use it as network storage (so really other devices push to or pull from *them*)$!![](https://guide-assets.appliedenergistics.org/minecraft-1.21.1/ae2/ae2-mechanics/import-export-storage_scene1.AEcrFt4JHXPG.png)/$The actions/events of pushing to and pulling from network storage are important to keep in mind when designing automation
and logistics setups.Storage PriorityPriorities can be set by clicking the wrench in the top-right of some GUIs.
Items entering the network will start at the highest priority storage, as
their first destination, in the case of two storages have the same priority,
if one already contains the item, they will prefer that storage over any
other. Any Whitelisted cells will be treated as already containing the item
when in the same priority group as other storages. Items being removed from storage will
be removed from the storage with the lowest priority. This priority system means as items are inserted and removed
from network storage, higher priority storages will be filled and lower priority storages will be emptied.

Minecraft  1.21.1  [[change](/)]
