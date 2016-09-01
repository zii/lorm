#coding: utf-8
import opcode
import dis

a = []
b = []
gi = (i for i in b if i<1)
print dir(gi)
print dir(gi.gi_frame)
print gi.gi_frame.f_locals['.0']
code = gi.gi_code.co_code
print map(ord, code)

dis.dis(code)

def interpret(gi):
    "python generator bytecode interpreter"
    gi_code = gi.gi_code
    consts = gi_code.co_consts
    code = gi_code.co_code
    print 'consts', consts
    print 'gi_code.co_varnames:', gi_code.co_varnames
    code = map(ord, code)
    i = 0
    size = len(code)
    while i < size:
        line = i
        op = code[i]
        opname = opcode.opname[op]
        arg = ''
        value = ''
        if op >= opcode.HAVE_ARGUMENT:
            arg = code[i+1] + (code[i+2] << 8)
            i += 3
        else:
            i += 1
        if opname == 'COMPARE_OP':
            value = opcode.cmp_op[arg]
        elif opname == 'LOAD_FAST':
            value = gi_code.co_varnames[arg]
            if value == '.0':
                value = gi.gi_frame.f_locals[value]
        elif opname == 'LOAD_CONST':
            value = consts[arg]
        print 'op:', line, opname, arg, value

interpret(gi)

