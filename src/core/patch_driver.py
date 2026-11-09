#!/usr/bin/env python3
"""
Deep patch engine for Linux USB serial drivers.

Completely neutralizes DTR and RTS assertion (pin pulled LOW) across all paths:
  1. Adds module parameter 'disable_dtr_rts' (default: true) so it can be
     toggled live via /sys/module/<name>/parameters/disable_dtr_rts without reloading!
  2. Overrides port_open: explicitly commands the chip to keep DTR/RTS inactive (HIGH/3.3V).
  3. Overrides tiocmset (ioctl TIOCMSET/TIOCMBIS): strips DTR/RTS from the 'set' mask,
     blocking any userspace app (PySerial, QtSerialPort, Gimbal GUI) from asserting DTR.
  4. Overrides dtr_rts: forces DTR/RTS to remain inactive (HIGH) on open and close.
  5. Overrides flow control: prevents DTR/RTS from being asserted in flow control registers.
"""

import sys
import re

SMART_BYPASS_HEADER = """
#include <linux/jiffies.h>
#include <linux/printk.h>

/* Added by uart_deep_patch: module parameter to disable DTR/RTS assertion */
static bool disable_dtr_rts = true;
module_param(disable_dtr_rts, bool, 0644);
MODULE_PARM_DESC(disable_dtr_rts, "Disable DTR/RTS assertion to prevent device reset (default: true)");

/* Added by uart_deep_patch: Smart sequence detection for flashing (Cải tiến 2) */
static bool smart_bypass = true;
module_param(smart_bypass, bool, 0644);
MODULE_PARM_DESC(smart_bypass, "Allow rapid multi-toggle flashing sequence while blocking single open (default: true)");

static int flash_detect_count = 0;
module_param(flash_detect_count, int, 0444);
MODULE_PARM_DESC(flash_detect_count, "Total number of firmware flashing sequences detected (read-only)");

static unsigned long last_toggle_jiffies = 0;
static int toggle_seq_count = 0;

static inline bool is_flashing_sequence(void)
{
	unsigned long now = jiffies;
	if (!smart_bypass)
	{
		return false;
	}

	if (time_after(now, last_toggle_jiffies + msecs_to_jiffies(600)))
	{
		toggle_seq_count = 1;
		last_toggle_jiffies = now;
		return false;
	}

	toggle_seq_count++;
	last_toggle_jiffies = now;
	if (toggle_seq_count == 2)
	{
		flash_detect_count++;
		pr_info("kernel-uart-patcher: Firmware flashing sequence detected (count: %d)! Temporarily bypassing DTR/RTS suppression\\n", flash_detect_count);
	}
	return (toggle_seq_count >= 2);
}
"""

def patch_cp210x(content: str) -> str:
    # 1. Add module parameter & smart bypass sequence detector
    target = '#include <linux/usb/serial.h>'
    if target not in content:
        raise ValueError("Target include not found in cp210x.c")
    content = content.replace(target, target + "\n" + SMART_BYPASS_HEADER, 1)

    # 2. Force DTR/RTS inactive immediately upon opening UART in cp210x_open
    open_pattern = re.compile(
        r'(result = cp210x_write_u16_reg\(port, CP210X_IFC_ENABLE, UART_ENABLE\);'
        r'\s+if \(result\) \{'
        r'\s+dev_err\(&port->dev, "%s - Unable to enable UART\\n", __func__\);'
        r'\s+return result;'
        r'\s+\})',
        re.MULTILINE
    )
    open_replacement = r"""\1

	if (disable_dtr_rts) {
		/* Deep patch: explicitly force DTR and RTS to HIGH (inactive) immediately on open */
		cp210x_write_u16_reg(port, CP210X_SET_MHS, CONTROL_WRITE_DTR | CONTROL_WRITE_RTS);
	}"""

    content, n = open_pattern.subn(open_replacement, content, count=1)
    if n == 0:
        raise ValueError("Failed to patch cp210x_open")

    # 3. Intercept cp210x_tiocmset_port specifically (Single open blocked, sequence pattern permitted)
    tiocmset_pattern = re.compile(
        r'(static int cp210x_tiocmset_port\(struct usb_serial_port \*port,\s*'
        r'unsigned int set, unsigned int clear\)\s*\{[^}]*?u16 control = 0;\s*int ret;)',
        re.MULTILINE | re.DOTALL
    )
    tiocmset_replacement = r"""\1

	if (disable_dtr_rts && !is_flashing_sequence()) {
		/* Deep patch: intercept and block single open DTR/RTS assertion */
		set &= ~(TIOCM_DTR | TIOCM_RTS);
		clear |= (TIOCM_DTR | TIOCM_RTS);
	}"""
    content, n = tiocmset_pattern.subn(tiocmset_replacement, content, count=1)
    if n == 0:
        raise ValueError("Failed to patch cp210x_tiocmset_port")

    # 4. Patch cp210x_dtr_rts
    dtr_pattern = re.compile(
        r'static void cp210x_dtr_rts\(struct usb_serial_port \*port, int on\)\s*\{'
        r'\s*if \(on\)\s*cp210x_tiocmset_port\(port, TIOCM_DTR \| TIOCM_RTS, 0\);'
        r'\s*else\s*cp210x_tiocmset_port\(port, 0, TIOCM_DTR \| TIOCM_RTS\);\s*\}',
        re.MULTILINE
    )
    dtr_replacement = """static void cp210x_dtr_rts(struct usb_serial_port *port, int on)
{
	if (disable_dtr_rts) {
		/* Deep patch: always force DTR/RTS inactive on port_open/close callback */
		cp210x_tiocmset_port(port, 0, TIOCM_DTR | TIOCM_RTS);
		return;
	}

	if (on)
		cp210x_tiocmset_port(port, TIOCM_DTR | TIOCM_RTS, 0);
	else
		cp210x_tiocmset_port(port, 0, TIOCM_DTR | TIOCM_RTS);
}"""
    content, n = dtr_pattern.subn(dtr_replacement, content, count=1)
    if n == 0:
        raise ValueError("Failed to patch cp210x_dtr_rts")

    # 5. Patch cp210x_set_flow_control: ensure port_priv->dtr is false when disabled
    flow_target = "if (port_priv->dtr)\n\t\tctl_hs |= CP210X_SERIAL_DTR_ACTIVE;"
    flow_replacement = """if (disable_dtr_rts) {
		port_priv->dtr = false;
		port_priv->rts = false;
	}

	if (port_priv->dtr)
		ctl_hs |= CP210X_SERIAL_DTR_ACTIVE;"""
    if flow_target not in content:
        raise ValueError("Failed to patch cp210x_set_flow_control")
    content = content.replace(flow_target, flow_replacement, 1)

    return content

def patch_ch341(content: str) -> str:
    # 1. Add module parameter & smart bypass sequence detector
    target = '#include <linux/usb/serial.h>'
    if target not in content:
        raise ValueError("Target include not found in ch341.c")
    content = content.replace(target, target + "\n" + SMART_BYPASS_HEADER, 1)

    # 2. Patch ch341_tiocmset
    tiocmset_pattern = re.compile(
        r'(static int ch341_tiocmset\(struct tty_struct \*tty,\s*'
        r'unsigned int set, unsigned int clear\)\s*\{[^}]*?u8 control;\s*)',
        re.MULTILINE | re.DOTALL
    )
    tiocmset_repl = r"""\1
	if (disable_dtr_rts && !is_flashing_sequence()) {
		set &= ~(TIOCM_DTR | TIOCM_RTS);
		clear |= (TIOCM_DTR | TIOCM_RTS);
	}
"""
    content, n = tiocmset_pattern.subn(tiocmset_repl, content, count=1)
    if n == 0:
        raise ValueError("Failed to patch ch341_tiocmset")

    # 3. Patch ch341_dtr_rts
    dtr_target = "if (on)\n\t\tpriv->mcr |= CH341_BIT_RTS | CH341_BIT_DTR;"
    dtr_repl = """if (disable_dtr_rts) {
		priv->mcr &= ~(CH341_BIT_RTS | CH341_BIT_DTR);
	} else if (on) {
		priv->mcr |= CH341_BIT_RTS | CH341_BIT_DTR;
	}"""
    if dtr_target not in content:
        raise ValueError("Failed to patch ch341_dtr_rts")
    content = content.replace(dtr_target, dtr_repl, 1)

    return content

def patch_ftdi(content: str) -> str:
    # 1. Add module parameter & smart bypass sequence detector
    target = '#include <linux/usb/serial.h>'
    if target not in content:
        raise ValueError("Target include not found in ftdi_sio.c")
    content = content.replace(target, target + "\n" + SMART_BYPASS_HEADER, 1)

    # 2. Patch update_mctrl
    target_mctrl = "clear &= ~set;\t/* 'set' takes precedence over 'clear' */"
    repl_mctrl = """if (disable_dtr_rts && !is_flashing_sequence()) {
		set &= ~(TIOCM_DTR | TIOCM_RTS);
		clear |= (TIOCM_DTR | TIOCM_RTS);
	}
	clear &= ~set;\t/* 'set' takes precedence over 'clear' */"""
    if target_mctrl not in content:
        raise ValueError("Failed to patch update_mctrl in ftdi_sio.c")
    content = content.replace(target_mctrl, repl_mctrl, 1)

    return content

def patch_cdc_acm(content: str) -> str:
    # 1. Add module parameter & smart bypass sequence detector
    target = '#include <linux/module.h>'
    if target not in content:
        raise ValueError("Target include not found in cdc-acm.c")
    content = content.replace(target, target + "\n" + SMART_BYPASS_HEADER, 1)

    # 2. Patch acm_port_dtr_rts
    dtr_target = "if (active)\n\t\tval = USB_CDC_CTRL_DTR | USB_CDC_CTRL_RTS;\n\telse\n\t\tval = 0;"
    dtr_repl = """if (disable_dtr_rts) {
\t\tval = 0;
\t} else if (active) {
\t\tval = USB_CDC_CTRL_DTR | USB_CDC_CTRL_RTS;
\t} else {
\t\tval = 0;
\t}"""
    if dtr_target in content:
        content = content.replace(dtr_target, dtr_repl, 1)
    else:
        dtr_pattern = re.compile(
            r'if\s*\(active\)\s*val\s*=\s*USB_CDC_CTRL_DTR\s*\|\s*USB_CDC_CTRL_RTS;\s*else\s*val\s*=\s*0;',
            re.MULTILINE
        )
        content, n = dtr_pattern.subn(dtr_repl, content, count=1)
        if n == 0:
            raise ValueError("Failed to patch acm_port_dtr_rts in cdc-acm.c")

    # 3. Patch acm_tty_tiocmset
    tiocmset_pattern = re.compile(
        r'(static int acm_tty_tiocmset\(struct tty_struct \*tty,\s*unsigned int set, unsigned int clear\)\s*\{)',
        re.MULTILINE
    )
    tiocmset_repl = r"""\1
	if (disable_dtr_rts && !is_flashing_sequence()) {
		set &= ~(TIOCM_DTR | TIOCM_RTS);
		clear |= (TIOCM_DTR | TIOCM_RTS);
	}"""
    content, n = tiocmset_pattern.subn(tiocmset_repl, content, count=1)
    if n == 0:
        raise ValueError("Failed to patch acm_tty_tiocmset in cdc-acm.c")

    return content

def patch_pl2303(content: str) -> str:
    # 1. Add module parameter & smart bypass sequence detector
    target = '#include <linux/usb/serial.h>'
    if target not in content:
        raise ValueError("Target include not found in pl2303.c")
    content = content.replace(target, target + "\n" + SMART_BYPASS_HEADER, 1)

    # 2. Patch pl2303_dtr_rts
    dtr_target = "if (on)\n\t\tpriv->line_control |= (CONTROL_DTR | CONTROL_RTS);\n\telse\n\t\tpriv->line_control &= ~(CONTROL_DTR | CONTROL_RTS);"
    dtr_repl = """if (disable_dtr_rts) {
\t\tpriv->line_control &= ~(CONTROL_DTR | CONTROL_RTS);
\t} else if (on) {
\t\tpriv->line_control |= (CONTROL_DTR | CONTROL_RTS);
\t} else {
\t\tpriv->line_control &= ~(CONTROL_DTR | CONTROL_RTS);
\t}"""
    if dtr_target in content:
        content = content.replace(dtr_target, dtr_repl, 1)
    else:
        dtr_pattern = re.compile(
            r'if\s*\(on\)\s*priv->line_control\s*\|=\s*\(CONTROL_DTR\s*\|\s*CONTROL_RTS\);\s*else\s*priv->line_control\s*&=.*?;',
            re.MULTILINE
        )
        content, n = dtr_pattern.subn(dtr_repl, content, count=1)
        if n == 0:
            raise ValueError("Failed to patch pl2303_dtr_rts in pl2303.c")

    # 3. Patch pl2303_tiocmset
    tiocmset_pattern = re.compile(
        r'(static int pl2303_tiocmset\(struct tty_struct \*tty,\s*unsigned int set, unsigned int clear\)\s*\{)',
        re.MULTILINE
    )
    tiocmset_repl = r"""\1
	if (disable_dtr_rts && !is_flashing_sequence()) {
		set &= ~(TIOCM_DTR | TIOCM_RTS);
		clear |= (TIOCM_DTR | TIOCM_RTS);
	}"""
    content, n = tiocmset_pattern.subn(tiocmset_repl, content, count=1)
    if n == 0:
        raise ValueError("Failed to patch pl2303_tiocmset in pl2303.c")

    return content

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <module_name> <source_file>")
        sys.exit(1)

    mod_name = sys.argv[1].lower().replace("-", "_")
    file_path = sys.argv[2]

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if mod_name == "cp210x":
        patched = patch_cp210x(content)
    elif mod_name == "ch341":
        patched = patch_ch341(content)
    elif mod_name in ("ftdi_sio", "ftdi"):
        patched = patch_ftdi(content)
    elif mod_name in ("cdc_acm", "cdc-acm"):
        patched = patch_cdc_acm(content)
    elif mod_name == "pl2303":
        patched = patch_pl2303(content)
    else:
        # Fallback for others: comment out .dtr_rts
        dtr_pattern = re.compile(r'^\s*\.dtr_rts\s*=.*', re.MULTILINE)
        patched = dtr_pattern.sub(
            '/* .dtr_rts disabled by uart_deep_patch */', content
        )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(patched)

    print(f"Successfully applied deep patch to {file_path} for {mod_name}")

if __name__ == "__main__":
    main()
