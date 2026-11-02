from pdfmeta.source_audit import assess


def test_syntactically_valid_formula_is_wrong_when_source_radical_is_missing():
    gold={'expected_latex':r'y=\sqrt{x^2-2x}','required_features':['sqrt']}
    assert assess({'status':'NORMALIZED','latex':'y=x^2-2x'},gold)=='WRONG'


def test_deferred_formula_is_not_counted_as_a_correct_prediction():
    assert assess(None,{'expected_latex':'y=x^2'})=='DEFERRED'
    assert assess({'status':'SOURCE_LAYOUT_UNRESOLVED','latex':None},{'expected_latex':'y=x^2'})=='DEFERRED'


def test_source_expression_comparison_preserves_function_and_derivative_identity():
    assert assess({'status':'NORMALIZED','latex':r"f'(x)=2x"},{'expected_latex':"f'(x)=2*x"})=='CORRECT'
    assert assess({'status':'NORMALIZED','latex':r'f(x)=2x'},{'expected_latex':"f'(x)=2*x"})=='WRONG'
