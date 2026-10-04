.PHONY: clean build run all

TEST_FLAGS ?=

all: clean build run

clean:
	rm -rf ./bin

build:
	mkdir -p ./bin
	clang ./src/tests.m -o ./bin/tests $(TEST_FLAGS) -DTESTS -DPROFILE=1 -F/System/Library/PrivateFrameworks -framework Carbon -framework Cocoa -framework CoreServices -framework CoreVideo -framework SkyLight

run:
	./bin/tests
