#coding: utf-8
import opcode
import dis

globals().update(opcode.opmap)

gi = (i for i,k in [] if 1 and 2.2/3/(i.id+1)<1)
print dir(gi)
print dir(gi.gi_code)
print gi.gi_frame.f_locals['.0']
print 'co_cellvars:', gi.gi_code.co_cellvars
print 'co_freevars:', gi.gi_code.co_freevars
print 'co_names:', gi.gi_code.co_names
#dis.dis(gi.gi_code)


def get_binary_priority(op):
    if op in (BINARY_POWER):
        return 1
    elif op in (BINARY_MULTIPLY, BINARY_DIVIDE, BINARY_MODULO, BINARY_FLOOR_DIVIDE, BINARY_TRUE_DIVIDE):
        return 2
    elif op in (BINARY_ADD, BINARY_SUBTRACT)
    elif op in (UNARY_POSITIVE, UNARY_NEGATIVE, UNARY_NOT, ):
        return 3

class Expression:
    def __init__(self, s, op):
        self.s = s
        self.op = op

    def __str__(self):
        return self.s

    def __repr__(self):
        return repr(self.s)



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
    stack = []
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
        
        if op == LOAD_FAST:
            value = gi_code.co_varnames[arg]
            if value == '.0':
                value = gi.gi_frame.f_locals[value]
                value = list(value)
            else:
                stack.append(value)
        elif op == STORE_FAST:
            value = gi_code.co_varnames[arg]
        elif op == LOAD_CONST:
            value = consts[arg]
            stack.append(value)
        elif op == LOAD_ATTR:
            value = gi_code.co_names[arg]
            top = stack.pop()
            exp = '%s%s%s' % (top, '.', value)
            stack.append(exp)
        elif op == BINARY_ADD:
            top = stack.pop()
            top2 = stack.pop()
            exp = '%s+%s' % (top2, top)
            stack.append(exp)
        elif op == BINARY_MULTIPLY:
            top = stack.pop()
            top2 = stack.pop()
            exp = '%s*%s' % (top2, top)
            stack.append(exp)
        elif op == COMPARE_OP:
            value = opcode.cmp_op[arg]
            top = stack.pop()
            top2 = stack.pop()
            exp = '%s%s%s' % (top2, value, top)
            stack.append(exp)
        elif op == POP_JUMP_IF_FALSE:
            jumpto = arg
            top = stack.pop()
            print top
        elif op == POP_JUMP_IF_TRUE:
            jumpto = arg
            top = stack.pop()
            print top
            
        print 'op:', line, opname, arg, value

interpret(gi)

