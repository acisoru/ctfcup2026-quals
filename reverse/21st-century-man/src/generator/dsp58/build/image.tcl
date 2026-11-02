# image.tcl -- Versal programmable device image: routed.dcp -> firmware.pdi
open_checkpoint routed.dcp
write_device_image -force firmware.pdi
