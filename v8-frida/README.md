# v8-frida

Experimental attempt of accessing internal v8 APIs from node binaries.
The goal is disassembling the bytecode for any version without recompiling v8.

But many hooks don't work as expected due to function inlining...

## Progress

- [x] disassemble top-level function

  ```js
  Parameter count 1
  Register count 1
  Frame size 8
  Bytecode age: 0
      0 S> 0x1b1569e37e5e @    0 : 80 00 00 00       CreateClosure [0], [0], #0
           0x1b1569e37e62 @    4 : c4                Star0
    242 S> 0x1b1569e37e63 @    5 : a9                Return
  Constant pool (size = 1)
  0x1b1569e37e69: [FixedArray] in OldSpace
  - map: 0x08c4b4080211 <Map(FIXED_ARRAY_TYPE)>
  - length: 1
            0: 0x1b1569e37e81 <SharedFunctionInfo>
  Handler Table (size = 0)
  Source Position Table (size = 7)
  0x1b1569e381f1 <ByteArray[7]>
  Process terminated
  [Local::node ]->

  Thank you for using Frida!
  ```

- [x] disassemble all functions
- [ ] print ArrayBoilerplateDescription
- [ ] print ObjectBoilerplateDescription
- [ ] print FixedArray
- [ ] print FixedDoubleArray
- [ ] works with multiple node versions
- [ ] works with multiple electron versions
- [ ] docker container

## Resources

- [Frida](https://frida.re/)
- [Frida Handbook](https://learnfrida.info)
