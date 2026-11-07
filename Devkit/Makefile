# Builds the samples and the deploy agent for Windows CE ARM with CeGCC.
#
#   make                 everything into Devkit/bin/
#   make hello agent     selected targets
#   CEGCC=/opt/cegcc-arm make      native toolchain instead of Docker
#   make deploy          copy bin/*.exe into the running emulator (needs ceagent on COM1:)
#
# Flags: _WIN32_WCE=0x600 selects the CE 6 API surface in the headers (the
# device runs CE 6.0; the emulator CE 7). -static keeps libgcc/libstdc++
# inside the binary, the device has no GCC runtime DLLs. The subsystem
# (9 = WINDOWS_CE_GUI) and the WinMainCRTStartup entry are the toolchain's
# defaults.
TOOL   := $(dir $(lastword $(MAKEFILE_LIST)))cegcc.sh
CC     := $(TOOL) arm-mingw32ce-gcc
CXX    := $(TOOL) arm-mingw32ce-g++
STRIP  := $(TOOL) arm-mingw32ce-strip
CFLAGS := -O2 -Wall -D_WIN32_WCE=0x600 -DUNICODE -D_UNICODE
LDFLAGS := -static -Wl,--image-base,0x10000
BIN    := bin

all: hello hellocpp agent

hello: $(BIN)/hello.exe
hellocpp: $(BIN)/hellocpp.exe
agent: $(BIN)/ceagent.exe

$(BIN):
	mkdir -p $(BIN)

$(BIN)/hello.exe: samples/hello/hello.c | $(BIN)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<
	$(STRIP) $@

$(BIN)/hellocpp.exe: samples/hello/hellocpp.cpp | $(BIN)
	$(CXX) $(CFLAGS) -std=c++17 $(LDFLAGS) -o $@ $<
	$(STRIP) $@

$(BIN)/ceagent.exe: agent/ceagent.c | $(BIN)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<
	$(STRIP) $@

# push everything to \My Flash Disk\dev in the emulator and run hello
deploy: all
	python3 deploy.py push $(BIN)/hello.exe $(BIN)/hellocpp.exe "\\My Flash Disk\\dev" --run --wait 10

clean:
	rm -rf $(BIN)

.PHONY: all hello hellocpp agent deploy clean
