static const uint64_t timing_bases[] = {
    0,
    86400ULL * 1000000000,
    7ULL * 86400 * 1000000000,
    30ULL * 86400 * 1000000000,
    1ULL << 60,
    UINT64_MAX - 2000000000
};

TEST_FUNC(elapsed_time_preserves_small_intervals,
{
    for (int i = 0; i < array_count(timing_bases); ++i) {
        uint64_t begin = timing_bases[i];
        TEST_CHECK(elapsed_time_ms(begin, begin) == 0.0, true);
        TEST_CHECK(fabs(elapsed_time_ms(begin, begin + 1) - 0.000001) < 1e-12, true);
        TEST_CHECK(elapsed_time_ms(begin, begin + 75000000) == 75.0, true);
        TEST_CHECK(elapsed_time_ms(begin, begin + 1500000000) == 1500.0, true);
        TEST_CHECK(elapsed_time_ms(begin, begin + 1249999999) < 1250.0, true);
        TEST_CHECK(elapsed_time_ms(begin, begin + 1250000000) >= 1250.0, true);
        TEST_CHECK(elapsed_time_ms(begin, begin + 1500000001) > 1500.0, true);
    }
});

TEST_FUNC(resize_throttle_threshold_is_independent_of_uptime,
{
    for (int i = 0; i < array_count(timing_bases); ++i) {
        uint64_t begin = timing_bases[i];
        TEST_CHECK(elapsed_time_ms(begin, begin + 67669999) < 67.67, true);
        TEST_CHECK(elapsed_time_ms(begin, begin + 67670000) >= 67.67, true);
        TEST_CHECK(elapsed_time_ms(begin, begin + 67670001) >= 67.67, true);
    }
});

