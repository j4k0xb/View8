# v8-frida

Experimental attempt of accessing internal v8 APIs from node binaries.
The goal is disassembling the bytecode for any version without recompiling v8.

But many hooks don't work as expected due to function inlining...

## Resources

- [Frida](https://frida.re/)
- [Frida Handbook](https://learnfrida.info)
