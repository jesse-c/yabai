#ifndef MESSAGE_H
#define MESSAGE_H

#define DAEMON_MESSAGE_MAX_LENGTH (1024 * 1024)
#define DAEMON_MESSAGE_MAX_CLIENTS 32
#define DAEMON_MESSAGE_TIMEOUT_MS 1000

enum daemon_request_state {
    DAEMON_REQUEST_READING,
    DAEMON_REQUEST_QUEUED,
    DAEMON_REQUEST_RESPONSE_READY,
    DAEMON_REQUEST_WRITING
};

struct daemon_request {
    int sockfd;
    enum daemon_request_state state;
    char header[sizeof(int)];
    size_t header_received;
    int length;
    size_t received;
    char *message;
    char *response;
    size_t response_length;
    size_t response_sent;
    uint64_t phase_begin;
};

void handle_message(FILE *rsp, char *message);
void message_handle_request(struct daemon_request *request);
bool message_loop_begin(char *socket_path);

#endif
