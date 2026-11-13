#include <stdio.h>
#include <sys/timex.h>
int main(void) {
    struct timex tx = {0};
    int state = adjtimex(&tx);
    if (state == -1) { perror("adjtimex"); return 1; }
    printf("state=%d status=%d offset_us=%ld frequency_scaled_ppm=%ld maxerror_us=%ld esterror_us=%ld tick_us=%ld\n", state, tx.status, tx.offset, tx.freq, tx.maxerror, tx.esterror, tx.tick);
    return 0;
}
