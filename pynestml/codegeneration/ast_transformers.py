#
# ast_transformers.py
#
# This file is part of NEST.
#
# Copyright (C) 2004 The NEST Initiative
#
# NEST is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# NEST is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with NEST.  If not, see <http://www.gnu.org/licenses/>.

import re

from typing import List, Mapping

from pynestml.codegeneration.expressions_pretty_printer import ExpressionsPrettyPrinter
from pynestml.symbols.variable_symbol import BlockType
from pynestml.meta_model.ast_assignment import ASTAssignment
from pynestml.meta_model.ast_declaration import ASTDeclaration
from pynestml.meta_model.ast_expression import ASTExpression
from pynestml.meta_model.ast_neuron import ASTNeuron
from pynestml.meta_model.ast_node_factory import ASTNodeFactory
from pynestml.meta_model.ast_ode_shape import ASTOdeShape
from pynestml.meta_model.ast_simple_expression import ASTSimpleExpression
from pynestml.meta_model.ast_variable import ASTVariable
from pynestml.utils.ast_source_location import ASTSourceLocation
from pynestml.symbols.predefined_functions import PredefinedFunctions
from pynestml.symbols.symbol import SymbolKind
from pynestml.utils.ast_utils import ASTUtils
from pynestml.utils.model_parser import ModelParser
from pynestml.utils.ode_transformer import OdeTransformer
from pynestml.visitors.ast_higher_order_visitor import ASTHigherOrderVisitor
from pynestml.visitors.ast_symbol_table_visitor import ASTSymbolTableVisitor


def add_declarations_to_internals(neuron: ASTNeuron, declarations: Mapping[str, str]) -> ASTNeuron:
    """
    Adds the variables as stored in the declaration tuples to the neuron.
    :param neuron: a single neuron instance
    :param declarations: a list of declaration tuples
    :return: a modified neuron
    """
    for variable in declarations:
        add_declaration_to_internals(neuron, variable, declarations[variable])
    return neuron


def add_declaration_to_internals(neuron: ASTNeuron, variable_name: str, init_expression: str) -> ASTNeuron:
    """
    Adds the variable as stored in the declaration tuple to the neuron. The declared variable is of type real.
    :param neuron: a single neuron instance
    :param variable_name: the name of the variable to add
    :param init_expression: initialization expression
    :return: the neuron extended by the variable
    """
    tmp = ModelParser.parse_expression(init_expression)
    vector_variable = ASTUtils.get_vectorized_variable(tmp, neuron.get_scope())

    declaration_string = variable_name + ' real' + (
        '[' + vector_variable.get_vector_parameter() + ']'
        if vector_variable is not None and vector_variable.has_vector_parameter() else '') + ' = ' + init_expression
    ast_declaration = ModelParser.parse_declaration(declaration_string)
    if vector_variable is not None:
        ast_declaration.set_size_parameter(vector_variable.get_vector_parameter())
    neuron.add_to_internal_block(ast_declaration)
    ast_declaration.update_scope(neuron.get_internals_blocks().get_scope())
    symtable_visitor = ASTSymbolTableVisitor()
    symtable_visitor.block_type_stack.push(BlockType.INTERNALS)
    ast_declaration.accept(symtable_visitor)
    symtable_visitor.block_type_stack.pop()
    return neuron


def add_declarations_to_initial_values(neuron: ASTNeuron, variables: List, initial_values: List) -> ASTNeuron:
    """
    Adds a single declaration to the initial values block of the neuron.
    :param neuron: a neuron
    :param declarations: a single
    :return: a modified neuron
    """
    for variable, initial_value in zip(variables, initial_values):
        add_declaration_to_initial_values(neuron, variable, initial_value)
    return neuron


def add_declaration_to_initial_values(neuron: ASTNeuron, variable: str, initial_value: str) -> ASTNeuron:
    """
    Adds a single declaration to the initial values block of the neuron. The declared variable is of type real.
    :param neuron: a neuron
    :param variable: state variable to add
    :param initial_value: corresponding initial value
    :return: a modified neuron
    """
    tmp = ModelParser.parse_expression(initial_value)
    vector_variable = ASTUtils.get_vectorized_variable(tmp, neuron.get_scope())
    declaration_string = variable + ' real' + (
        '[' + vector_variable.get_vector_parameter() + ']'
        if vector_variable is not None and vector_variable.has_vector_parameter() else '') + ' = ' + initial_value
    ast_declaration = ModelParser.parse_declaration(declaration_string)
    if vector_variable is not None:
        ast_declaration.set_size_parameter(vector_variable.get_vector_parameter())
    neuron.add_to_initial_values_block(ast_declaration)
    ast_declaration.update_scope(neuron.get_initial_values_blocks().get_scope())

    symtable_visitor = ASTSymbolTableVisitor()
    symtable_visitor.block_type_stack.push(BlockType.INITIAL_VALUES)
    ast_declaration.accept(symtable_visitor)
    symtable_visitor.block_type_stack.pop()

    return neuron


def declaration_in_initial_values(neuron: ASTNeuron, variable_name: str) -> bool:
    assert type(variable_name) is str

    for decl in neuron.get_initial_values_blocks().get_declarations():
        for var in decl.get_variables():
            if var.get_complete_name() == variable_name:
                return True

    return False


def apply_incoming_spikes(neuron: ASTNeuron):
    """
    Adds a set of update instructions to the handed over neuron.
    :param neuron: a single neuron instance
    :type neuron: ASTNeuron
    :return: the modified neuron
    :rtype: ASTNeuron
    """
    assert (neuron is not None and isinstance(neuron, ASTNeuron)), \
        '(PyNestML.Solver.BaseTransformer) No or wrong type of neuron provided (%s)!' % type(neuron)
    conv_calls = OdeTransformer.get_sum_function_calls(neuron)
    printer = ExpressionsPrettyPrinter()
    spikes_updates = list()
    for convCall in conv_calls:
        shape = convCall.get_args()[0].get_variable().get_complete_name()
        buffer = convCall.get_args()[1].get_variable().get_complete_name()
        initial_values = (
            neuron.get_initial_values_blocks().get_declarations() if neuron.get_initial_values_blocks() is not None else list())
        for astDeclaration in initial_values:
            for variable in astDeclaration.get_variables():
                if re.match(shape + "[\']*", variable.get_complete_name()) or re.match(shape + '__[\\d]+$',
                                                                                       variable.get_complete_name()):
                    spikes_updates.append(ModelParser.parse_assignment(
                        variable.get_complete_name() + " += " + buffer + " * " + printer.print_expression(
                            astDeclaration.get_expression())))
    for update in spikes_updates:
        add_assignment_to_update_block(update, neuron)
    return neuron


def add_assignment_to_update_block(assignment: ASTAssignment, neuron: ASTNeuron) -> ASTNeuron:
    """
    Adds a single assignment to the end of the update block of the handed over neuron.
    :param assignment: a single assignment
    :param neuron: a single neuron instance
    :return: the modified neuron
    """
    small_stmt = ASTNodeFactory.create_ast_small_stmt(assignment=assignment,
                                                      source_position=ASTSourceLocation.get_added_source_position())
    stmt = ASTNodeFactory.create_ast_stmt(small_stmt=small_stmt,
                                          source_position=ASTSourceLocation.get_added_source_position())
    if not neuron.get_update_blocks():
        neuron.create_empty_update_block()
    neuron.get_update_blocks().get_block().get_stmts().append(stmt)
    small_stmt.update_scope(neuron.get_update_blocks().get_block().get_scope())
    stmt.update_scope(neuron.get_update_blocks().get_block().get_scope())
    return neuron


def add_declaration_to_update_block(declaration: ASTDeclaration, neuron: ASTNeuron) -> ASTNeuron:
    """
    Adds a single declaration to the end of the update block of the handed over neuron.
    :param declaration: ASTDeclaration node to add
    :param neuron: a single neuron instance
    :return: a modified neuron
    """
    small_stmt = ASTNodeFactory.create_ast_small_stmt(declaration=declaration,
                                                      source_position=ASTSourceLocation.get_added_source_position())
    stmt = ASTNodeFactory.create_ast_stmt(small_stmt=small_stmt,
                                          source_position=ASTSourceLocation.get_added_source_position())
    if not neuron.get_update_blocks():
        neuron.create_empty_update_block()
    neuron.get_update_blocks().get_block().get_stmts().append(stmt)
    small_stmt.update_scope(neuron.get_update_blocks().get_block().get_scope())
    stmt.update_scope(neuron.get_update_blocks().get_block().get_scope())
    return neuron


def add_state_updates(neuron: ASTNeuron, update_expressions: Mapping[str, str]) -> ASTNeuron:
    """
    Adds all update instructions as contained in the solver output to the update block of the neuron.
    :param state_shape_variables_updates: map of variables to corresponding updates during the update step.
    :param neuron: a single neuron
    :return: a modified version of the neuron
    """
    for variable, update_expression in update_expressions.items():
        declaration_statement = variable + '__tmp real = ' + update_expression
        add_declaration_to_update_block(ModelParser.parse_declaration(declaration_statement), neuron)
    for variable, update_expression in update_expressions.items():
        add_assignment_to_update_block(ModelParser.parse_assignment(variable + ' = ' + variable + '__tmp'), neuron)
    return neuron



def variable_in_neuron_initial_values(name: str, neuron: ASTNeuron):
    for decl in neuron.get_initial_blocks().get_declarations():
        assert len(decl.get_variables()) == 1, "Multiple declarations in the same statement not yet supported"
        if decl.get_variables()[0].get_complete_name() == name:
            return True
    return False


def variable_in_solver(shape_var: str, solver_dicts):
    """Check if a variable by this name is defined in the ode-toolbox solver results
    """

    for solver_dict in solver_dicts:
        if solver_dict is None:
            continue

        for var_name in solver_dict["state_variables"]:
            var_name_base = var_name.split("__X__")[0]
            #var_name_base = var_name_base.split("__d")[0]
            if var_name_base == shape_var:
                return True

    return False



def is_ode_variable(var_base_name, neuron):
    equations_block = neuron.get_equations_blocks()
    for ode_eq in equations_block.get_ode_equations():
        var = ode_eq.get_lhs()
        if var.get_name() == var_base_name:
            return True
    return False


def variable_in_shapes(var_name: str, shapes):
    """Check if a variable by this name (in ode-toolbox style) is defined in the ode-toolbox solver results
    """

    var_name_base = var_name.split("__X__")[0]
    var_name_base = var_name_base.split("__d")[0]
    var_name_base = var_name_base.replace("__DOLLAR", "$")

    for shape in shapes:
        for shape_var in shape.get_variables():
            if var_name_base == shape_var.get_name():
                return True

    return False


def get_initial_value_from_odetb_result(var_name: str, solver_dicts):
    """Get the initial value of the variable with the given name from the ode-toolbox results JSON.

    N.B. the variable name is given in ode-toolbox notation.
    """

    for solver_dict in solver_dicts:
        if solver_dict is None:
            continue

        if var_name in solver_dict["state_variables"]:
            return solver_dict["initial_values"][var_name]

    assert False, "Initial value not found for ODE with name \"" + var_name + "\""


def get_shape_var_order_from_ode_toolbox_result(shape_var: str, solver_dicts):
    """Get the differential order of the variable with the given name from the ode-toolbox results JSON.

    N.B. the variable name is given in NESTML notation, e.g. "g_in$"; convert to ode-toolbox export format notation (e.g. "g_in__DOLLAR").
    """

    shape_var = shape_var.replace("$", "__DOLLAR")

    order = -1
    for solver_dict in solver_dicts:
        if solver_dict is None:
            continue

        for var_name in solver_dict["state_variables"]:
            var_name_base = var_name.split("__X__")[0]
            var_name_base = var_name_base.split("__d")[0]
            if var_name_base == shape_var:
                order = max(order, var_name.count("__d") + 1)

    assert order >= 0, "Variable of name \"" + shape_var + "\" not found in ode-toolbox result"
    return order



def to_odetb_processed_name(name: str) -> str:
    """convert name in the same way as ode-toolbox does from input to output, i.e. returned names are compatible with ode-toolbox output"""
    return name.replace("$", "__DOLLAR").replace("'", "__d")


def to_odetb_name(name: str) -> str:
    """convert to a name suitable for ode-toolbox input"""
    return name.replace("$", "__DOLLAR")


def get_expr_from_shape_var(shape, var_name):
    assert type(var_name) == str
    for var, expr in zip(shape.get_variables(), shape.get_expressions()):
        if var.get_complete_name() == var_name:
            return expr
    assert False, "variable name not found in shape"


def construct_shape_X_spike_buf_name(shape_var_name: str, spike_input_port, order: int, diff_order_symbol="__d"):
    assert type(shape_var_name) is str
    assert type(order) is int
    assert type(diff_order_symbol) is str
    return shape_var_name.replace("$", "__DOLLAR") + "__X__" + str(spike_input_port) + diff_order_symbol * order



def replace_rhs_variable(expr, variable_name_to_replace, shape_var, spike_buf):
    def replace_shape_var(node):
        if type(node) is ASTSimpleExpression \
            and node.is_variable() \
            and node.get_variable().get_name() == variable_name_to_replace:
            var_order = node.get_variable().get_differential_order()
            new_variable_name = construct_shape_X_spike_buf_name(shape_var.get_name(), spike_buf, var_order - 1, diff_order_symbol="'")
            new_variable = ASTVariable(new_variable_name, var_order)
            new_variable.set_source_position(node.get_variable().get_source_position())
            node.set_variable(new_variable)

    expr.accept(ASTHigherOrderVisitor(visit_funcs=replace_shape_var))


def replace_rhs_variables(expr, shape_buffers):
    """
    Replace variable names in definitions of shape dynamics.

    Say that the shape is

    .. code-block::

        G = -G / tau

    Its variable symbol might be replaced by "G__X__spikesEx":

    .. code-block::

        G__X__spikesEx = -G / tau

    This function updates the right-hand side of `expr` so that it would also read (in this example):

    .. code-block::

        G__X__spikesEx = -G__X__spikesEx / tau

    These equations will later on be fed to ode-toolbox, so we use the symbol "'" to indicate differential order.

    Note that for shapes/systems of ODE of dimension > 1, all variable orders and all variables for this shape will already be present in `shape_buffers`.
    """
    for shape, spike_buf in shape_buffers:
        for shape_var in shape.get_variables():
            variable_name_to_replace = shape_var.get_name()
            replace_rhs_variable(expr, variable_name_to_replace=variable_name_to_replace, shape_var=shape_var, spike_buf=spike_buf)




def is_delta_shape(shape):
    """catches definition of shape, or reference (function call or variable name) of a delta shape function"""
    if type(shape) is ASTOdeShape:
        if not len(shape.get_variables()) == 1:
            # delta shape not allowed if more than one variable is defined in this shape
            return False
        expr = shape.get_expressions()[0]
    else:
        expr = shape

    rhs_is_delta_shape = type(expr) is ASTSimpleExpression \
        and expr.is_function_call() \
        and expr.get_function_call().get_scope().resolve_to_symbol(expr.get_function_call().get_name(), SymbolKind.FUNCTION) == PredefinedFunctions.name2function["delta"]
    rhs_is_multiplied_delta_shape = type(expr) is ASTExpression \
        and type(expr.get_rhs()) is ASTSimpleExpression \
        and expr.get_rhs().is_function_call() \
        and expr.get_rhs().get_function_call().get_scope().resolve_to_symbol(expr.get_rhs().get_function_call().get_name(), SymbolKind.FUNCTION) == PredefinedFunctions.name2function["delta"]
    #is_name_of_delta_shape = type(expr) is ASTSimpleExpression \
        #and expr.is_variable() \
        #and expr.get_variable().get_scope().resolve_to_symbol(expr.get_variable().get_name(), SymbolKind.VARIABLE).is_shape() \
        #and expr.
    return rhs_is_delta_shape or rhs_is_multiplied_delta_shape


def get_delta_shape_prefactor_expr(shape):
    assert type(shape) is ASTOdeShape
    assert len(shape.get_variables()) == 1
    expr = shape.get_expressions()[0]
    if type(expr) is ASTExpression \
     and expr.get_rhs().is_function_call() \
     and expr.get_rhs().get_function_call().get_scope().resolve_to_symbol(expr.get_rhs().get_function_call().get_name(), SymbolKind.FUNCTION) == PredefinedFunctions.name2function["delta"] \
     and expr.binary_operator.is_times_op:
        return str(expr.lhs)



