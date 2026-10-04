static void request_test_dispose(struct daemon_request *request, int peer)
{
    close(peer);
    close(request->sockfd);
    free(request->message);
}

TEST_FUNC(daemon_request_reader_assembles_fragmented_frames, {
    int sockets[2];
    TEST_CHECK(socketpair(AF_UNIX, SOCK_STREAM, 0, sockets), 0);
    struct daemon_request request = {0};
    request.sockfd = sockets[1];
    request.phase_begin = read_os_timer();
    char payload[] = "config\0debug_output\0";
    int length = sizeof(payload);
    for (size_t i = 0; i < sizeof(length); ++i) {
        TEST_CHECK((int)write(sockets[0], (char *)&length + i, 1), 1);
        TEST_CHECK(message_request_read(&request), MESSAGE_READ_WAIT);
    }
    for (int i = 0; i < length; ++i) {
        TEST_CHECK((int)write(sockets[0], payload + i, 1), 1);
        TEST_CHECK(message_request_read(&request), i == length-1 ? MESSAGE_READ_READY : MESSAGE_READ_WAIT);
    }
    TEST_CHECK(memcmp(request.message, payload, sizeof(payload)), 0);
    char *cursor = request.message;
    TEST_CHECK(token_equals(get_token(&cursor), "config"), true);
    TEST_CHECK(token_equals(get_token(&cursor), "debug_output"), true);
    for (int i = 0; i < 100; ++i) TEST_CHECK(get_token(&cursor).length, 0);
    request_test_dispose(&request, sockets[0]);
})

static const int request_test_bad_lengths[] = {-1, 0, 1, DAEMON_MESSAGE_MAX_LENGTH+1, INT_MIN, INT_MAX};

TEST_FUNC(daemon_request_reader_rejects_invalid_sizes_and_termination, {
    for (int i = 0; i < array_count(request_test_bad_lengths); ++i) {
        int sockets[2];
        TEST_CHECK(socketpair(AF_UNIX, SOCK_STREAM, 0, sockets), 0);
        struct daemon_request request = {0};
        request.sockfd = sockets[1];
        request.phase_begin = read_os_timer();
        TEST_CHECK((int)write(sockets[0], &request_test_bad_lengths[i], sizeof(int)), (int)sizeof(int));
        TEST_CHECK(message_request_read(&request), MESSAGE_READ_INVALID);
        TEST_CHECK(request.message == NULL, true);
        request_test_dispose(&request, sockets[0]);
    }
    for (int i = 0; i < 3; ++i) {
        int sockets[2];
        TEST_CHECK(socketpair(AF_UNIX, SOCK_STREAM, 0, sockets), 0);
        struct daemon_request request = {0};
        request.sockfd = sockets[1];
        request.phase_begin = read_os_timer();
        int length = 2;
        char payload[2] = {0};
        if (i < 2) payload[i] = 'x';
        TEST_CHECK((int)write(sockets[0], &length, sizeof(length)), (int)sizeof(length));
        TEST_CHECK((int)write(sockets[0], payload, sizeof(payload)), (int)sizeof(payload));
        TEST_CHECK(message_request_read(&request), i == 2 ? MESSAGE_READ_READY : MESSAGE_READ_INVALID);
        request_test_dispose(&request, sockets[0]);
    }
    int sockets[2];
    TEST_CHECK(socketpair(AF_UNIX, SOCK_STREAM, 0, sockets), 0);
    struct daemon_request request = {0};
    request.sockfd = sockets[1];
    request.phase_begin = read_os_timer() - read_os_freq();
    TEST_CHECK(message_request_read(&request), MESSAGE_READ_INVALID);
    request_test_dispose(&request, sockets[0]);
})

static int request_test_connect(char *path)
{
    int fd = -1;
    if (!socket_open(&fd) || !socket_connect(fd, path)) return -1;
    message_socket_prepare(fd);
    return fd;
}

static void request_test_send_query(int fd)
{
    char payload[] = "config\0debug_output\0";
    int length = sizeof(payload);
    assert(write(fd, &length, sizeof(length)) == sizeof(length));
    assert(write(fd, payload, sizeof(payload)) == sizeof(payload));
}

static struct event *request_test_take(void)
{
    uint64_t begin = read_os_timer();
    struct event *event;
    do {
        event = event_loop_take(&g_event_loop, false);
        if (event) return event;
        usleep(1000);
    } while (elapsed_time_ms(begin, read_os_timer()) < 500);
    return NULL;
}

static bool request_test_read_response(int fd, bool failure, int timeout)
{
    struct pollfd socket = {0};
    socket.fd = fd;
    socket.events = POLLIN;
    if (poll(&socket, 1, timeout) <= 0) return false;
    char response[256] = {0};
    ssize_t n = recv(fd, response, sizeof(response)-1, MSG_DONTWAIT);
    if (n <= 0) return false;
    return failure ? response[0] == FAILURE_MESSAGE[0] : strcmp(response, "off\n") == 0;
}

TEST_FUNC(daemon_socket_worker_isolates_slow_clients_and_bounds_admission, {
    char path[100];
    snprintf(path, sizeof(path), "/tmp/yabai-request-test-%d.socket", getpid());
    TEST_CHECK(event_loop_init(&g_event_loop), true);
    bool started = message_loop_begin(path);
    TEST_CHECK(started, true);
    if (!started) {
        fprintf(stderr, "test listener initialization: %s\n", strerror(errno));
        pthread_cond_destroy(&g_event_loop.ready);
        pthread_mutex_destroy(&g_event_loop.lock);
        return false;
    }

    int idle = request_test_connect(path);
    int partial = request_test_connect(path);
    int length = 32;
    TEST_CHECK((int)write(partial, &length, sizeof(length)), (int)sizeof(length));
    TEST_CHECK((int)write(partial, "x", 1), 1);
    int healthy = request_test_connect(path);
    request_test_send_query(healthy);
    struct event *event = request_test_take();
    TEST_CHECK(event != NULL, true);
    if (event) {
        TEST_CHECK(event->type, DAEMON_MESSAGE);
        EVENT_HANDLER_DAEMON_MESSAGE(event->context, event->param1);
        free(event);
    }
    TEST_CHECK(request_test_read_response(healthy, false, 200), true);
    TEST_CHECK(event_loop_take(&g_event_loop, false) == NULL, true);
    TEST_CHECK(request_test_read_response(idle, true, 1500), true);
    TEST_CHECK(request_test_read_response(partial, true, 1500), true);
    close(idle); close(partial); close(healthy);

    // A peer that does not consume its large response must not block a second
    // command. The writer also has a deadline independent of the event thread.
    int slow = request_test_connect(path);
    request_test_send_query(slow);
    event = request_test_take();
    TEST_CHECK(event != NULL, true);
    if (event) {
        struct daemon_request *request = event->context;
        request->response_length = 8 * 1024 * 1024;
        request->response = malloc(request->response_length);
        memset(request->response, 'x', request->response_length);
        __atomic_store_n(&request->state, DAEMON_REQUEST_RESPONSE_READY, __ATOMIC_RELEASE);
        message_loop_wake();
        free(event);
    }
    healthy = request_test_connect(path);
    request_test_send_query(healthy);
    event = request_test_take();
    TEST_CHECK(event != NULL, true);
    if (event) { EVENT_HANDLER_DAEMON_MESSAGE(event->context, event->param1); free(event); }
    TEST_CHECK(request_test_read_response(healthy, false, 200), true);
    close(healthy);
    usleep((DAEMON_MESSAGE_TIMEOUT_MS + 100) * 1000);
    size_t received = 0;
    char buffer[65536];
    ssize_t n;
    while ((n = recv(slow, buffer, sizeof(buffer), MSG_DONTWAIT)) > 0) received += (size_t)n;
    TEST_CHECK(n == 0, true);
    TEST_CHECK(received < 8 * 1024 * 1024, true);
    close(slow);

    int clients[DAEMON_MESSAGE_MAX_CLIENTS];
    for (int i = 0; i < DAEMON_MESSAGE_MAX_CLIENTS; ++i) clients[i] = request_test_connect(path);
    int extra = request_test_connect(path);
    TEST_CHECK(request_test_read_response(extra, true, 200), true);
    close(extra);
    for (int i = 0; i < DAEMON_MESSAGE_MAX_CLIENTS; ++i) close(clients[i]);

    __atomic_store_n(&g_message_loop.is_running, false, __ATOMIC_RELEASE);
    message_loop_wake();
    pthread_join(g_message_loop.thread, NULL);
    close(g_message_loop.sockfd);
    close(g_message_loop.wakeup[0]); close(g_message_loop.wakeup[1]);
    unlink(path);
    TEST_CHECK(event_loop_take(&g_event_loop, false) == NULL, true);
    pthread_cond_destroy(&g_event_loop.ready);
    pthread_mutex_destroy(&g_event_loop.lock);
})
