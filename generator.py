#coding: utf-8
"""Decompile generator object to SQL."""
import opcode
import dis

# define opcode constants
globals().update(opcode.opmap)


def get_op_priority(op):
    if op in (BINARY_POWER):
        return 5
    elif op in (BINARY_MULTIPLY, BINARY_DIVIDE, BINARY_MODULO, BINARY_FLOOR_DIVIDE, BINARY_TRUE_DIVIDE):
        return 4
    elif op in (BINARY_ADD, BINARY_SUBTRACT):
        return 3
    elif op in (BINARY_LSHIFT, BINARY_RSHIFT, BINARY_AND, BINARY_XOR, BINARY_OR):
        return 2
    elif op in (UNARY_POSITIVE, UNARY_NEGATIVE, UNARY_NOT):
        return 1
    return 0


class Expression:
    def __init__(self, s, op):
        self.s = s
        self.op = op
        self.prio = get_op_priority(op)
    
    def __str__(self):
        return self.s

    def __add__(self, e):
        if e.prio < self.prio:
            return ""

    def __repr__(self):
        return repr(self.s)


class Instruction:
    def __init__(self, line, op, arg=None, value=None):
        self.line = line
        self.op = op
        self.arg = arg
        self.value = value

    def __cmp__(self, other):
        return cmp(self.line, other.line)

    def __str__(self):
        opname = opcode.opname[self.op]
        line = str(self.line)
        s = "%s %s" % (line.ljust(4), opname.ljust(20))
        if self.arg is not None:
            s += " %s" % self.arg
        if self.value is not None:
            s += " (%s)" % self.value
        return s

def find_inst(insts, op, reverse=True):
    iter = reversed(insts) if reverse else insts
    ops = op if isinstance(op, (tuple, list)) else [op]
    for i, inst in enumerate(iter):
        if inst.op in ops:
            return len(insts)-i if reverse else i
    return -1

def print_insts(insts):
    for i in insts:
        print i

class Decompiler:
    def __init__(self, gi):
        self.gi = gi
        self.gi_code = gi_code = gi.gi_code
        self.bytes = map(ord, gi_code.co_code)
        self.consts = gi_code.co_consts
        self.varnames = gi_code.co_varnames
        self.names = gi_code.co_names
        self.f_locals = gi.gi_frame.f_locals
        self.insts = []
        self.inst_map = {} # {line: Instruction}
        self.field_insts = []
        self.cond_insts = []
    
    def d1(self):
        "pass one: translate bytes to instruction sequence"
        insts = []
        inst_map = {}
        bytes = self.bytes
        
        size = len(bytes)
        i = 0
        while i < size:
            line = i
            op = bytes[i]
            opname = opcode.opname[op]
            arg = None
            value = None
            if op >= opcode.HAVE_ARGUMENT:
                arg = bytes[i+1] + (bytes[i+2] << 8)
                i += 3
            else:
                i += 1
            
            if op == LOAD_FAST:
                value = self.varnames[arg]
                if value == '.0':
                    value = self.f_locals[value]
                    value = list(value)
            elif op == STORE_FAST:
                value = self.varnames[arg]
            elif op == LOAD_CONST:
                value = self.consts[arg]
            elif op == LOAD_ATTR:
                value = self.names[arg]
            elif op == COMPARE_OP:
                value = opcode.cmp_op[arg]
            
            inst = Instruction(line, op, arg, value)
            insts.append(inst)
            inst_map[line] = inst
        
        self.insts = insts
        self.inst_map = inst_map
    
    def d2(self):
        "pass two: split instructions into two parts, fields sequence and condition sequence."
        insts = self.insts
        end_i = find_inst(insts, YIELD_VALUE)
        assert end_i >= 0
        end_i -= 1
        start_i = find_inst(insts, STORE_FAST)
        assert start_i >= 0
        jump_i = find_inst(insts, (POP_JUMP_IF_FALSE, POP_JUMP_IF_TRUE))
        if jump_i >= 0:
            field_insts = insts[start_i:jump_i]
            cond_insts = insts[jump_i:end_i]
        else:
            field_insts = insts[start_i:end_i]
            cond_insts = []
        self.field_insts = field_insts
        self.cond_insts = cond_insts
    
    def d(self):
        bytes = self.bytes
        
        i = 0
        size = len(bytes)
        stack = []
        while i < size:
            line = i
            op = bytes[i]
            opname = opcode.opname[op]
            arg = ''
            value = ''
            if op >= opcode.HAVE_ARGUMENT:
                arg = bytes[i+1] + (bytes[i+2] << 8)
                i += 3
            else:
                i += 1
            
            if op == LOAD_FAST:
                value = self.varnames[arg]
                if value == '.0':
                    value = gi.gi_frame.f_locals[value]
                    value = list(value)
                else:
                    stack.append(value)
            elif op == STORE_FAST:
                value = self.varnames[arg]
            elif op == LOAD_CONST:
                value = self.consts[arg]
                stack.append(value)
            elif op == LOAD_ATTR:
                value = self.names[arg]
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
                if top is None:
                    top = 'null'
                if arg > 5:
                    value = ' %s ' % value
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

if __name__ == '__main__':
    gi = (i for i,k in [] if +i<<1 is not None and 2.2/3/(i.id+1)<1)
    #print dir(gi)
    #print dir(gi.gi_code)
    print gi.gi_frame.f_locals['.0']
    print 'co_cellvars:', gi.gi_code.co_cellvars
    print 'co_freevars:', gi.gi_code.co_freevars
    print 'co_names:', gi.gi_code.co_names
    print 'co_consts:', gi.gi_code.co_consts
    print 'co_varnames:', gi.gi_code.co_varnames
    #dis.dis(gi.gi_code)
    print '-----------'

    d = Decompiler(gi)
    d.d1()
    d.d2()
#     for i in d.insts:
#         print i
    
    print '---- FIELD INSTS ----'
    print_insts(d.field_insts)
    print '---- COND INSTS ----'
    print_insts(d.cond_insts)
    
    