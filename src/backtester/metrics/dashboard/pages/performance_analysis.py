import streamlit as st

st.set_page_config(layout="wide")
st.title("Performance Analysis")

st.write(st.session_state.df)