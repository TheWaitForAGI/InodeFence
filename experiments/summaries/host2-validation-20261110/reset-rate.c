#include <stdio.h>
#include <sys/timex.h>
int main(void) {
    struct timex before = {0}, change = {0}, after = {0};
    if (adjtimex(&before) < 0) { perror("read before"); return 1; }
    printf("before status=%d tick_us=%ld freq_scaled_ppm=%ld\n", before.status, before.tick, before.freq);
    fflush(stdout);
    change.modes = ADJ_TICK | ADJ_FREQUENCY;
    change.tick = 10000;
    change.freq = 0;
    if (adjtimex(&change) < 0) { perror("set rate"); return 2; }
    if (adjtimex(&after) < 0) { perror("read after"); return 3; }
    printf("after status=%d tick_us=%ld freq_scaled_ppm=%ld\n", after.status, after.tick, after.freq);
    return 0;
}
