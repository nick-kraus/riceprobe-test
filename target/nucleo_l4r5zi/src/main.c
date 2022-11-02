#include <zephyr/drivers/pwm.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/shell/shell.h>

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

static const struct pwm_dt_spec pwm_led = PWM_DT_SPEC_GET(DT_ALIAS(pwm_led0));

static struct k_timer led_fade_timer;
void led_fade_fn(struct k_timer *timer) {
	const int32_t period = 100000;
	static int32_t pulse_width = 0;
	static int32_t step = period / 50;

	int32_t ret = pwm_set_dt(&pwm_led, period, pulse_width);
	if (ret < 0) {
		LOG_ERR("pwm set failed with error %d", ret);
		k_timer_stop(timer);
	}

	pulse_width += step;
	if (pulse_width >= period) {
		pulse_width = period;
		step *= -1;
	} else if (pulse_width <= 0) {
		pulse_width = 0;
		step *= -1;
	}
}

int32_t cmd_test_dump(const struct shell *shell, size_t argc, char **argv) {
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	for (int32_t i = 0; i < 1600; i+=8) {
		shell_info(
			shell,
			"0x%08x 0x%08x 0x%08x 0x%08x 0x%08x 0x%08x 0x%08x 0x%08x",
			i, i+1, i+2, i+3, i+4, i+5, i+6, i+7
		);
	}

	return 0;
}

int32_t cmd_test_var(const struct shell *shell, size_t argc, char **argv) {
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	static volatile int32_t var = 0;
	shell_info(shell, "int 'var' address: %p", &var);
	shell_info(shell, "int 'var' value: 0x%08x", var);

	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(test_subcmds,
	SHELL_CMD(dump, NULL, "dump large amount of data to shell", cmd_test_dump),
	SHELL_CMD(var, NULL, "print address and value of an i32 variable", cmd_test_var),
	SHELL_SUBCMD_SET_END
);
SHELL_CMD_REGISTER(test, &test_subcmds, "test commands", NULL);

void main(void) {

	if (!device_is_ready(pwm_led.dev)) {
		LOG_ERR("PWM device %s not ready", pwm_led.dev->name);
		return;
	}

	k_timer_init(&led_fade_timer, led_fade_fn, NULL);
	k_timer_start(&led_fade_timer, K_NO_WAIT, K_MSEC(25));
}
