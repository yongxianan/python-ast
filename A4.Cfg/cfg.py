from var_ast import VarAst
from common import remove_block_from_list

import ast
import common
import copy


class BlockList(list):
    def get_block(self, block_to_find):
        for block in self.__iter__():
            if common.is_blocks_same(block, block_to_find):
                return block

    def get_block_by_name(self, name):
        for block in self.__iter__():
            if block.name == name:
                return block


class RawBasicBlock:
    BLOCK_IF = 0
    BLOCK_WHILE = 1

    IS_TRUE_BLOCK = 0
    IS_FALSE_BLOCK = 1

    def __init__(self, start_line=None, end_line=None, block_end_type=None, name=None):
        if not (isinstance(start_line, int) or not isinstance(end_line, int))\
                and start_line is not None and end_line is not None:
            raise TypeError
        self._start_line = start_line
        self._end_line = end_line
        self._block_end_type = block_end_type
        self.nxt_block_list = []
        self.prev_block_list = []
        self.dominates_list = []
        self.df = []
        self.name = name
        self.var_kill = set()
        self.ue_var = set()

    @property
    def start_line(self):
        return self._start_line
        
    @start_line.setter
    def start_line(self, start_line):
        if not isinstance(start_line, int):
            raise TypeError
        self._start_line = start_line

    @property
    def end_line(self):
        return self._end_line

    @end_line.setter
    def end_line(self, end_line):
        if not isinstance(end_line, int):
            raise TypeError
        self._end_line = end_line

    @property
    def block_end_type(self):
        return self._block_end_type

    @block_end_type.setter
    def block_end_type(self, block_end_type):
        self._block_end_type = block_end_type

    def __repr__(self):
        s = "Block {} from line {} to {}".format(self.name, self.start_line, self.end_line)
        return s

    def get_num_of_parents(self):
        return len(self.prev_block_list)


class Cfg:
    def __init__(self, as_tree=None, *basic_block_args):
        self.__else_flag__ = False
        self.block_list = []
        self.dominator_tree = DominatorTree()
        self.globals_var = set()
        self.block_set = {}

        if as_tree is not None:
            self.as_tree = as_tree
            self.root, _ = self.parse(as_tree.body)

        if len(basic_block_args) != 0:
            for basic_block in basic_block_args:
                self.add_basic_block(basic_block)

    def add_basic_block(self, basic_block):
        if basic_block.start_line is not None:
            self.block_list.append(basic_block)

    @staticmethod
    def get_basic_block(ast_body):
        """
        yield all simple block in the ast, non recursively
        :param ast_body: ast structure
        :return: yield all simple block
        """
        basic_block = RawBasicBlock(start_line=ast_body[0].lineno)
        for ast_node in ast_body:
            if basic_block.start_line is None:
                basic_block.start_line = ast_node.lineno
            basic_block.end_line = ast_node.lineno
            if common.is_if_stmt(ast_node) or common.is_while_stmt(ast_node):
                # self.add_basic_block(basic_block)
                basic_block.block_end_type = ast_node.__class__.__name__
                basic_block.name = 'L' + str(basic_block.start_line)
                yield basic_block
                basic_block = RawBasicBlock()

        if basic_block.start_line is not None:
            basic_block.name = 'L' + str(basic_block.start_line)
            yield basic_block

    def get_ast_node(self, ast_tree, lineno):
        for node in ast.iter_child_nodes(ast_tree):

            if node.lineno == lineno:
                return node

            if isinstance(node, ast.If) or isinstance(node, ast.While):
                node_return = self.get_ast_node(node, lineno)
                if node_return is not None:
                    return node_return
                continue

        return None

    def link_tail_to_cur_block(self, all_tail_list, basic_block):
        for tail in all_tail_list:
            self.connect_2_blocks(tail, basic_block)

    def build_if_body(self, if_block):
        all_tail_list = []
        ast_if_node = self.get_ast_node(self.as_tree, if_block.end_line)
        head_returned, tail_list = self.parse(ast_if_node.body)

        self.connect_2_blocks(if_block, head_returned)
        all_tail_list.extend(tail_list)

        head_returned, tail_list = self.parse(ast_if_node.orelse)
        if head_returned is not None:
            # has an else or elif
            self.connect_2_blocks(if_block, head_returned)
            all_tail_list.extend(tail_list)
        else:
            # no else
            # link this to the next statement
            all_tail_list.append(if_block)

        return all_tail_list

    def build_while_body(self, while_block):
        all_tail_list = []
        ast_while_node = self.get_ast_node(self.as_tree, while_block.end_line)
        head_returned, tail_list = self.parse(ast_while_node.body)

        self.connect_2_blocks(while_block, head_returned)
        self.link_tail_to_cur_block(tail_list, while_block)
        all_tail_list.append(while_block)
        return all_tail_list

    def parse(self, ast_body):
        head = None
        all_tail_list = []
        if len(ast_body) == 0:
            return head, all_tail_list
        for basic_block in self.get_basic_block(ast_body):

            if len(all_tail_list) == 0:
                head = basic_block
            else:
                pass
                self.link_tail_to_cur_block(all_tail_list, basic_block)

            all_tail_list = []
            self.add_basic_block(basic_block)

            if basic_block.block_end_type == 'If':
                tail_list = self.build_if_body(basic_block)
                all_tail_list.extend(tail_list)

            elif basic_block.block_end_type == 'While':
                while_block = self.separate_while_block(basic_block)

                tail_list = self.build_while_body(while_block)
                all_tail_list.extend(tail_list)

            else:
                all_tail_list.append(basic_block)

        return head, all_tail_list

    def separate_block(self, basic_block):
        separated_block = RawBasicBlock(basic_block.end_line, basic_block.end_line)
        basic_block.end_line -= 1
        self.connect_2_blocks(basic_block, separated_block)
        return separated_block

    def separate_while_block(self, basic_block):
        while_block = self.separate_block(basic_block)

        while_block.block_end_type = 'While'
        basic_block.block_end_type = None
        self.add_basic_block(while_block)
        return while_block

    @staticmethod
    def connect_2_blocks(block1, block2):
        """
        connect block 1 to block 2
        :param block1:
        :param block2:
        :return:
        """
        block1.nxt_block_list.append(block2)
        block2.prev_block_list.append(block1)
    
    def fill_df(self):
        self.dominator_tree.build(self.root, self.block_list)

    def get_var_ast(self, block):
        for i in range(block.start_line, block.end_line + 1):
            ast_stmt = self.get_ast_node(self.as_tree, i)
            var_ast = VarAst(ast_stmt)
            yield var_ast.targets_var, var_ast.values_var

    def gather_initial_info(self):
        for block in self.block_list:
            for targets, values in self.get_var_ast(block):
                for value in values:
                    if value not in block.var_kill:
                        block.ue_var.add(value)
                        self.globals_var.add(value)
                block.var_kill |= set(targets)
                for target in targets:
                    if self.block_set.get(target) is None:
                        self.block_set[target] = [block]
                    else:
                        if block not in self.block_set[target]:
                            self.block_set[target].append(block)


class DominatorTree:
    def __init__(self, cfg=None):
        self.dominator_root = None
        self.dominator_nodes = BlockList()
        if cfg is not None:
            self.cfg = cfg

    def build(self, root, block_list):
        self.fill_dominates(root, block_list)
        self.build_tree(root)
        self.fill_df(block_list)

    def fill_dominates(self, cfg_root, block_list):
        for removed_block_num in (range(len(block_list))):
            dom_root = copy.deepcopy(cfg_root)
            dom_block_list = copy.copy(block_list)
            # remove the block
            # walk again
            dom_root = common.delete_node(dom_root, block_list[removed_block_num])

            for not_dom_block in common.walk_block(dom_root):
                remove_block_from_list(dom_block_list, not_dom_block)

            remove_block_from_list(dom_block_list, block_list[removed_block_num])
            block_list[removed_block_num].dominates_list.extend(dom_block_list)
            del dom_root

    def build_tree(self, root):
        # TODO: clarify the code below
        for block_in_cfg in common.walk_block(root):
            block_in_dom_list = RawBasicBlock(block_in_cfg.start_line, block_in_cfg.end_line)
            self.dominator_nodes.append(block_in_dom_list)
            for dom_block in block_in_cfg.dominates_list:
                dom_block_in_dom_list = self.dominator_nodes.get_block(dom_block)
                if not dom_block_in_dom_list.prev_block_list:
                    Cfg.connect_2_blocks(block_in_dom_list, dom_block_in_dom_list)

        self.dominator_root = self.dominator_nodes[-1]

    def fill_df(self, block_list):
        for nodes in block_list:
            if nodes.get_num_of_parents() > 1:
                for pred_node in nodes.prev_block_list:
                    runner = pred_node
                    while not common.is_blocks_same(self.dominator_nodes.get_block(runner),
                                                    self.get_idom(block_list, nodes)) \
                            and runner is not None:
                        runner.df.append(nodes)
                        runner = self.get_idom(block_list, runner)

    def get_idom(self, block_list, cfg_node):
        dom_node = self.dominator_nodes.get_block(cfg_node)
        if dom_node.prev_block_list:
            cfg_idom_node = common.find_node(block_list, dom_node.prev_block_list[0])
            return cfg_idom_node
        return None


def build_blocks(*args, block_links):
    block_list = []
    for i in range(len(args)):
        basic_block = RawBasicBlock(args[i][0], args[i][1], args[i][2])

        block_list.append(basic_block)

    for i in range(len(block_links)):
        nxt_block_list = block_links.get(str(i))
        for nxt_block_num in nxt_block_list:
            Cfg.connect_2_blocks(block_list[i], block_list[nxt_block_num])

    return block_list
