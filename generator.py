#coding: utf-8
"""Decompile generator object to SQL."""
import opcode
import dis
import datetime

# define opcode constants
globals().update(opcode.opmap)

BINOP_SET = set([
    BINARY_MULTIPLY, BINARY_DIVIDE, BINARY_MODULO, BINARY_FLOOR_DIVIDE,
    BINARY_TRUE_DIVIDE, BINARY_LSHIFT, BINARY_RSHIFT, BINARY_AND, BINARY_XOR,
    BINARY_OR, BINARY_ADD, BINARY_SUBTRACT, BINARY_POWER,
])

OP_TOKENS = {
    BINARY_MULTIPLY: '*',
    BINARY_DIVIDE: '/',
    BINARY_MODULO: '%',
    BINARY_FLOOR_DIVIDE: '/',
    BINARY_TRUE_DIVIDE: '/',
    BINARY_LSHIFT: '<<',
    BINARY_RSHIFT: '>>',
    BINARY_AND: '&',
    BINARY_XOR: '^',
    BINARY_OR: '|',
    BINARY_ADD: '+',
    BINARY_SUBTRACT: '-',
}

FUNC_ALIAS = {
    'unixtime': 'UNIX_TIMESTAMP',
    'from_unixtime': 'FROM_UNIXTIME',
}

def get_op_priority(op):
    if op in (LOAD_GLOBAL, LOAD_FAST, LOAD_CONST, LOAD_DEREF, LOAD_ATTR,
              CALL_FUNCTION, BUILD_TUPLE, BUILD_LIST):
        return 7
    elif op in opcode.hasjabs:
        return 7
    elif op in (BINARY_POWER, ):
        return 6
    elif op in (BINARY_MULTIPLY, BINARY_DIVIDE, BINARY_MODULO, BINARY_FLOOR_DIVIDE, BINARY_TRUE_DIVIDE):
        return 5
    elif op in (BINARY_ADD, BINARY_SUBTRACT, UNARY_POSITIVE, UNARY_NEGATIVE):
        return 4
    elif op in (BINARY_LSHIFT, BINARY_RSHIFT, BINARY_AND, BINARY_XOR, BINARY_OR):
        return 3
    elif op in (COMPARE_OP, ):
        return 2
    elif op in (UNARY_NOT, ):
        return 1
    return 0

def get_op_token(op):
    return OP_TOKENS.get(op)

def escape_string(value):
    """escape_string escapes *value* but not surround it with quotes.

    Value should be bytes or unicode.
    """
    if isinstance(value, unicode):
        value = str(value)
    assert isinstance(value, (bytes, bytearray))
    value = value.replace('\\', '\\\\')
    value = value.replace('\0', '\\0')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\032', '\\Z')
    value = value.replace("'", "\\'")
    value = value.replace('"', '\\"')
    return value

def escape(o):
    if isinstance(o, basestring):
        return escape_string(o)
    elif o is None:
        return 'NULL'
    elif isinstance(o, datetime.datetime):
        return "%s" % o.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(o, datetime.date):
        return "%s" % o.strftime('%Y-%m-%d')
    return str(o)

def literal(o):
    if isinstance(o, basestring):
        return "'%s'" % escape_string(o)
    elif o is None:
        return 'NULL'
    elif isinstance(o, (tuple, list)):
        s = ','.join(literal(r) for r in o)
        return "(%s)" % s
    elif isinstance(o, datetime.datetime):
        return "'%s'" % o.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(o, datetime.date):
        return "'%s'" % o.strftime('%Y-%m-%d')
    return str(o)

class Expression:
    def __init__(self, op, v, atom=False, o=None):
        self.v = v
        self.op = op
        self.atom = atom
        self.prio = get_op_priority(op)
        self.o = o

    @property
    def escape(self):
        if self.o:
            return escape(self.o)
        return str(self.v)

    @property
    def literal(self):
        if self.o:
            return literal(self.o)
        v = self.v
        if self.op == LOAD_FAST:
            return "%s.*" % v
        return literal(v) if self.atom else str(v)

    def brackets(self, op):
        p = get_op_priority(op)
        if p > self.prio:
            return '(%s)' % self.literal
        return self.literal

    def __str__(self):
        return self.literal

    def __repr__(self):
        return self.literal

    def __unicode__(self):
        return unicode(self.literal)

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
            s += " (%s)" % str(self.value)
        return s

def find_inst(insts, op, reverse=True, arg=None):
    iter = reversed(insts) if reverse else insts
    ops = op if isinstance(op, (tuple, list)) else [op]
    for i, inst in enumerate(iter):
        if inst.op in ops and (arg is None or arg==inst.arg):
            return len(insts)-i if reverse else i
    return -1

def print_insts(insts):
    for i in insts:
        print i

class UnsupportOp(Exception):
    def __init__(self, op):
        self.opname = opcode.opname[op]

    def __str__(self):
        return self.opname

class Decompiler:
    def __init__(self, gi):
        self.gi = gi
        self.gi_code = gi_code = gi.gi_code
        self.bytes = map(ord, gi_code.co_code)
        self.consts = gi_code.co_consts
        self.varnames = gi_code.co_varnames
        self.freevars = gi_code.co_freevars
        self.names = gi_code.co_names
        self.f_locals = gi.gi_frame.f_locals
        self.f_globals = gi.gi_frame.f_globals
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
            elif op == LOAD_GLOBAL:
                value = self.names[arg]
            elif op == LOAD_DEREF:
                value = self.freevars[arg]
            elif op == STORE_FAST:
                value = self.varnames[arg]
            elif op == LOAD_CONST:
                value = self.consts[arg]
            elif op == LOAD_ATTR:
                value = self.names[arg]
            elif op == COMPARE_OP:
                if arg == 2: #==
                    value = '='
                else:
                    value = opcode.cmp_op[arg]
            elif op == CALL_FUNCTION:
                value = arg
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
        jump_i = find_inst(insts, POP_JUMP_IF_FALSE, arg=3)
        if jump_i >= 0:
            cond_insts = insts[start_i:jump_i]
            field_insts = insts[jump_i:end_i]
        else:
            field_insts = insts[start_i:end_i]
            cond_insts = []
        self.field_insts = field_insts
        self.cond_insts = cond_insts

    def explain_cond(self, insts, start, end):
        "decompile expression"
        if not insts:
            return

        stack = []
        def push(op, v):
            stack.append(Expression(op, v))
        def pusho(op, v, o=None):
            stack.append(Expression(op, v, True, o))
        pop = lambda: stack.pop()
        pop2 = lambda: (stack.pop(), stack.pop())
        i = start
        while i < end:
            inst = insts[i]
            op = inst.op
            v  = inst.value
            if op == LOAD_FAST:
                pusho(op, v)
            elif op == LOAD_CONST:
                pusho(op, v, v)
            elif op == LOAD_GLOBAL:
                pusho(op, v, self.f_globals.get(v))
            elif op == LOAD_DEREF:
                pusho(op, v, self.f_locals.get(v))
            elif op == LOAD_ATTR:
                top = pop()
                if top.o:
                    o = getattr(top.o, v)
                    pusho(top.op, '%s.%s' % (top.v, v), o)
                else:
                    push(op, '%s.%s' % (top.v, v))
            elif op == UNARY_POSITIVE:
                top = pop()
                s = top.brackets(op)
                push(op, '+%s' % s)
            elif op == UNARY_NEGATIVE:
                top = pop()
                s = top.brackets(op)
                push(op, '-%s' % s)
            elif op == BINARY_POWER:
                b, a = pop2()
                s = 'POWER(%s,%s)' % (a, b)
                push(op, s)
            elif op in BINOP_SET:
                b, a = pop2()
                a = a.brackets(op)
                b = b.brackets(op)
                tok = get_op_token(op)
                s = '%s%s%s' % (a, tok, b)
                push(op, s)
            elif op == COMPARE_OP:
                b, a = pop2()
                if v > 5:
                    s = '%s %s %s' % (a, v, b)
                else:
                    s = '%s%s%s' % (a, v, b)
                push(op, s)
            elif op == CALL_FUNCTION:
                args = [pop() for _ in xrange(inst.arg)]
                args.reverse()
                f = pop()
                real_call = False
                if f.o:
                    arg_list = [arg.o for arg in args]
                    if all(arg_list):
                        v = f.o(*arg_list)
                        pusho(f.op, v, v)
                        real_call = True
                if not real_call:
                    f = str(f.v)
                    row = f.rsplit('.', 1)
                    if len(row) > 1:
                        this, func_name = row
                    else:
                        func_name, this = f, None
                    func_name = FUNC_ALIAS.get(func_name) or func_name
                    if this:
                        args.insert(0, this)
                    s = '%s(%s)'%(func_name, ','.join(str(arg) for arg in args))
                    push(op, s)
            elif op in (BUILD_TUPLE, BUILD_LIST):
                row = [pop() for _ in xrange(inst.arg)]
                row.reverse()
                pusho(op, row, row)
            else:
                raise UnsupportOp(op)

            i += 1

        assert len(stack) == 1, stack
        return stack.pop()


def test():
    from lorm import Struct
    a = Struct()
    a.x = 1
    now = datetime.datetime.now()
    #gi = (i+1>2**i.id+1 for i,k in [] if +i<<1 is not None and 2.2/3/(i.id+1)<1)
    gi = (1 if (0 or 2) and (3 if i and (4 or 4) else 0) and 3 else 0 for i in [])
    print gi.gi_frame.f_locals['.0']
    print 'co_cellvars:', gi.gi_code.co_cellvars
    print 'co_freevars:', gi.gi_code.co_freevars
    print 'co_names:', gi.gi_code.co_names
    print 'co_consts:', gi.gi_code.co_consts
    print 'co_varnames:', gi.gi_code.co_varnames
    dis.dis(gi.gi_code)
    print '-----------'

    d = Decompiler(gi)
    d.d1()
    d.d2()

    print locals()['d']

    print '---- FIELD INSTS ----'
    print_insts(d.field_insts)
    print '---- COND INSTS ----'
    print_insts(d.cond_insts)
    exp = d.explain_cond(d.field_insts, 0, len(d.field_insts))
    print 'cond express:', str(exp)

if __name__ == '__main__':
    test()
